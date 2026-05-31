"""Tkinter front-end for the auto-cut tool.

Pure standard-library GUI (no extra deps). The actual work runs on a background
thread so the window stays responsive, and progress is marshalled back to the
Tk main thread via a thread-safe queue.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

from .audio_analysis import AnalysisSettings, AudioAnalysisError
from .processor import CutResult, run_autocut
from .resolve_api import ResolveConnection, ResolveError, connect

_GREEN = "#2e7d32"
_RED = "#c62828"
_GREY = "#666666"


class AutoCutApp(ttk.Frame):
    """Main application frame."""

    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=12)
        self.master.title("DaVinci Resolve Auto-Cut")
        self.master.minsize(460, 520)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self._conn: ResolveConnection | None = None
        self._events: "queue.Queue[tuple]" = queue.Queue()

        self._threshold = tk.DoubleVar(value=-40.0)
        self._min_silence = tk.DoubleVar(value=0.5)
        self._padding = tk.IntVar(value=150)

        self._build_widgets()
        self.after(100, self._drain_events)

    # -- layout ---------------------------------------------------------------

    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        row = 0

        # Connection section.
        conn_frame = ttk.LabelFrame(self, text="Connection", padding=10)
        conn_frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        conn_frame.columnconfigure(1, weight=1)
        self._connect_btn = ttk.Button(
            conn_frame, text="Connect to Resolve", command=self._on_connect
        )
        self._connect_btn.grid(row=0, column=0, sticky="w")
        self._status = ttk.Label(conn_frame, text="Not connected", foreground=_GREY)
        self._status.grid(row=0, column=1, sticky="w", padx=(10, 0))
        row += 1

        # Settings section.
        settings = ttk.LabelFrame(self, text="Settings", padding=10)
        settings.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        settings.columnconfigure(1, weight=1)

        self._add_slider(
            settings, 0, "Silence threshold (dB)", self._threshold, -60.0, 0.0, "{:.0f}"
        )
        self._add_slider(
            settings, 1, "Min silence (seconds)", self._min_silence, 0.1, 3.0, "{:.2f}"
        )

        ttk.Label(settings, text="Padding (ms)").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Spinbox(
            settings, from_=0, to=1000, increment=10, width=8, textvariable=self._padding
        ).grid(row=2, column=1, sticky="w", padx=(10, 0))
        row += 1

        # Action.
        self._cut_btn = ttk.Button(
            self, text="Cut Timeline", command=self._on_cut, state="disabled"
        )
        self._cut_btn.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        row += 1

        self._progress = ttk.Progressbar(self, mode="indeterminate")
        self._progress.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        row += 1

        # Log output.
        log_frame = ttk.LabelFrame(self, text="Log", padding=6)
        log_frame.grid(row=row, column=0, sticky="nsew")
        self.rowconfigure(row, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self._log = tk.Text(log_frame, height=8, wrap="word", state="disabled")
        self._log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, command=self._log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self._log.configure(yscrollcommand=scroll.set)

    def _add_slider(self, parent, row, label, var, lo, hi, fmt) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        value_lbl = ttk.Label(parent, text=fmt.format(var.get()), width=6)
        value_lbl.grid(row=row, column=2, sticky="e")
        scale = ttk.Scale(
            parent,
            from_=lo,
            to=hi,
            variable=var,
            command=lambda _v, lbl=value_lbl, v=var, f=fmt: lbl.config(text=f.format(v.get())),
        )
        scale.grid(row=row, column=1, sticky="ew", padx=(10, 6))

    # -- event helpers (run on Tk thread) ------------------------------------

    def _log_line(self, message: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", message + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _set_status(self, text: str, color: str) -> None:
        self._status.configure(text=text, foreground=color)

    # -- connect --------------------------------------------------------------

    def _on_connect(self) -> None:
        self._connect_btn.configure(state="disabled")
        self._set_status("Connecting...", _GREY)
        threading.Thread(target=self._connect_worker, daemon=True).start()

    def _connect_worker(self) -> None:
        try:
            conn = connect()
            name = conn.current_timeline_name()
        except ResolveError as exc:
            self._events.put(("connect_error", str(exc)))
            return
        self._events.put(("connect_ok", (conn, name)))

    # -- cut ------------------------------------------------------------------

    def _on_cut(self) -> None:
        if self._conn is None:
            return
        self._cut_btn.configure(state="disabled")
        self._connect_btn.configure(state="disabled")
        self._progress.start(12)
        settings = AnalysisSettings(
            silence_threshold_db=float(self._threshold.get()),
            min_silence_seconds=float(self._min_silence.get()),
            padding_ms=int(self._padding.get()),
        )
        self._log_line(
            f"Starting auto-cut (threshold {settings.silence_threshold_db:.0f} dB, "
            f"min silence {settings.min_silence_seconds:.2f}s, "
            f"padding {settings.padding_ms} ms)..."
        )
        threading.Thread(
            target=self._cut_worker, args=(settings,), daemon=True
        ).start()

    def _cut_worker(self, settings: AnalysisSettings) -> None:
        def progress(message: str) -> None:
            self._events.put(("log", message))

        try:
            result = run_autocut(self._conn, settings, progress=progress)
        except (ResolveError, AudioAnalysisError) as exc:
            self._events.put(("cut_error", str(exc)))
            return
        except Exception as exc:  # pragma: no cover - last-resort guard
            self._events.put(("cut_error", f"Unexpected error: {exc}"))
            return
        self._events.put(("cut_ok", result))

    # -- queue pump -----------------------------------------------------------

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self._events.get_nowait()
                self._handle_event(kind, payload)
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _handle_event(self, kind: str, payload) -> None:
        if kind == "log":
            self._log_line(payload)
        elif kind == "connect_ok":
            self._conn, name = payload
            self._set_status("Connected", _GREEN)
            self._log_line(f"Connected. Current timeline: {name!r}")
            self._connect_btn.configure(state="normal")
            self._cut_btn.configure(state="normal")
        elif kind == "connect_error":
            self._set_status("Not connected", _RED)
            self._log_line(f"Connection failed:\n{payload}")
            self._connect_btn.configure(state="normal")
        elif kind == "cut_ok":
            self._finish_cut()
            result: CutResult = payload
            self._log_line(
                f"Done. Created timeline {result.new_timeline_name!r} with "
                f"{result.segments_kept} segment(s) from {result.clips_analyzed} clip(s)."
            )
            if result.skipped_clips:
                self._log_line(
                    f"Skipped {len(result.skipped_clips)} silent/unreadable clip(s): "
                    + ", ".join(result.skipped_clips)
                )
        elif kind == "cut_error":
            self._finish_cut()
            self._log_line(f"Cut failed:\n{payload}")

    def _finish_cut(self) -> None:
        self._progress.stop()
        self._cut_btn.configure(state="normal")
        self._connect_btn.configure(state="normal")


def main() -> None:
    root = tk.Tk()
    AutoCutApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
