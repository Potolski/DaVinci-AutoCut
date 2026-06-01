"""Tkinter front-end for the auto-cut tool.

Pure standard-library GUI (no extra deps), styled to feel at home next to
DaVinci Resolve: a dark, borderless window with a custom title bar, flat
controls and Resolve-like sliders. The actual work runs on a background thread
so the window stays responsive, and progress is marshalled back to the Tk main
thread via a thread-safe queue.
"""

from __future__ import annotations

import os
import queue
import sys
import tempfile
import threading
import tkinter as tk
import traceback
from tkinter import font as tkfont
from tkinter import ttk

from .audio_analysis import AnalysisSettings, AudioAnalysisError
from .processor import CutResult, run_autocut
from .resolve_api import ResolveConnection, ResolveError, connect

# DaVinci-Resolve-like dark palette.
C_BORDER = "#0b0d10"
C_BASE = "#23262c"   # window / panel
C_TITLE = "#15171b"  # title bar
C_INPUT = "#101216"  # troughs, log, slider rails
C_FIELD = "#333942"  # buttons, combobox/spinbox fields
C_FIELD_HI = "#3d444e"
C_FG = "#d6dae0"
C_MUTED = "#868e99"
C_ACCENT = "#5bc8f2"  # logo cyan
C_ACCENT_DK = "#2f93c4"
C_OK = "#5bd08a"
C_ERR = "#e26d6d"

_AUDIO_TRACK_CHOICES = {
    "Auto (most speech)": "auto",
    "All tracks (any sound)": "all",
    "Track 1": 1,
    "Track 2": 2,
    "Track 3": 3,
    "Track 4": 4,
}


def _crash_log_path() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "davinci-autocut-error.log")
    return os.path.join(tempfile.gettempdir(), "davinci-autocut-error.log")


def _format_unexpected(exc: BaseException) -> str:
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    path = _crash_log_path()
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(tb)
    except OSError:
        path = "(could not write log file)"
    return (
        f"Unexpected error: {type(exc).__name__}: {exc}\n"
        f"Full details saved to:\n  {path}"
    )


def _pick_font(root, candidates, size, weight="normal"):
    """Return the first installed font family from ``candidates``."""
    available = set(tkfont.families(root))
    family = next((f for f in candidates if f in available), candidates[-1])
    return tkfont.Font(root=root, family=family, size=size, weight=weight)


class AutoCutApp:
    """Main application controller (builds into a borderless root window)."""

    def __init__(self, root: tk.Tk, resolve_obj=None):
        self.root = root
        self._resolve_obj = resolve_obj
        self._conn: ResolveConnection | None = None
        self._events: "queue.Queue[tuple]" = queue.Queue()
        self._drag = (0, 0)

        self._threshold = tk.DoubleVar(value=-40.0)
        self._min_silence = tk.DoubleVar(value=0.5)
        self._padding = tk.IntVar(value=150)
        self._audio_track = tk.StringVar(value="Auto (most speech)")

        self._init_fonts()
        self._init_style()
        self._build()

        self.root.after(100, self._drain_events)
        if self._resolve_obj is not None:
            self.root.after(150, self._on_connect)

    # -- theme ---------------------------------------------------------------

    def _init_fonts(self) -> None:
        sans = ["Segoe UI", "Helvetica Neue", "DejaVu Sans", "TkDefaultFont"]
        self.f_base = _pick_font(self.root, sans, 10)
        self.f_small = _pick_font(self.root, sans, 9)
        self.f_title = _pick_font(self.root, ["Segoe UI Semibold", "Segoe UI"] + sans, 11, "bold")
        self.f_head = _pick_font(self.root, sans, 8, "bold")
        self.f_mono = _pick_font(self.root, ["Consolas", "Menlo", "DejaVu Sans Mono", "TkFixedFont"], 9)

    def _init_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure(".", background=C_BASE, foreground=C_FG,
                        font=self.f_base, borderwidth=0, focuscolor=C_BASE)
        style.configure("TFrame", background=C_BASE)
        style.configure("TLabel", background=C_BASE, foreground=C_FG)
        style.configure("Muted.TLabel", foreground=C_MUTED)
        style.configure("Head.TLabel", foreground=C_MUTED, font=self.f_head)
        style.configure("Value.TLabel", foreground=C_ACCENT, font=self.f_small)

        # Flat buttons.
        style.configure("TButton", background=C_FIELD, foreground=C_FG,
                        borderwidth=0, focusthickness=0, padding=(12, 7))
        style.map("TButton",
                  background=[("active", C_FIELD_HI), ("disabled", "#2a2e35")],
                  foreground=[("disabled", "#5a626c")])

        style.configure("Accent.TButton", background=C_ACCENT, foreground="#08222e",
                        font=self.f_title, padding=(12, 9))
        style.map("Accent.TButton",
                  background=[("active", "#74d3f5"), ("disabled", "#2a2e35")],
                  foreground=[("disabled", "#5a626c")])

        # Sliders (clam draws the thumb with 'background').
        style.configure("Horizontal.TScale", background=C_ACCENT,
                        troughcolor=C_INPUT, borderwidth=0)
        style.map("Horizontal.TScale", background=[("active", "#74d3f5")])

        # Combobox / spinbox.
        for name in ("TCombobox", "TSpinbox"):
            style.configure(name, fieldbackground=C_FIELD, background=C_FIELD,
                            foreground=C_FG, arrowcolor=C_FG, borderwidth=0,
                            padding=4, selectbackground=C_FIELD, selectforeground=C_FG)
        style.map("TCombobox", fieldbackground=[("readonly", C_FIELD)],
                  selectbackground=[("readonly", C_FIELD)], selectforeground=[("readonly", C_FG)])
        self.root.option_add("*TCombobox*Listbox.background", C_FIELD)
        self.root.option_add("*TCombobox*Listbox.foreground", C_FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", C_ACCENT_DK)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

        style.configure("Horizontal.TProgressbar", background=C_ACCENT,
                        troughcolor=C_INPUT, borderwidth=0)
        style.configure("Vertical.TScrollbar", background=C_FIELD, troughcolor=C_INPUT,
                        arrowcolor=C_MUTED, borderwidth=0)
        style.map("Vertical.TScrollbar", background=[("active", C_FIELD_HI)])

    # -- layout --------------------------------------------------------------

    def _build(self) -> None:
        self.root.configure(bg=C_BORDER)
        # 1px border: inner container inset by 1px reveals the border colour.
        outer = tk.Frame(self.root, bg=C_BASE)
        outer.pack(fill="both", expand=True, padx=1, pady=1)

        self._build_titlebar(outer)

        body = ttk.Frame(outer, padding=(16, 12, 16, 14))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        row = 0

        # Connection.
        self._section(body, row, "CONNECTION"); row += 1
        conn = ttk.Frame(body)
        conn.grid(row=row, column=0, sticky="ew", pady=(2, 10)); row += 1
        conn.columnconfigure(1, weight=1)
        self._connect_btn = ttk.Button(conn, text="Connect to Resolve", command=self._on_connect)
        self._connect_btn.grid(row=0, column=0, sticky="w")
        self._status = ttk.Label(conn, text="Not connected", style="Muted.TLabel")
        self._status.grid(row=0, column=1, sticky="w", padx=(12, 0))

        # Settings.
        self._section(body, row, "SETTINGS"); row += 1
        settings = ttk.Frame(body)
        settings.grid(row=row, column=0, sticky="ew", pady=(2, 10)); row += 1
        settings.columnconfigure(1, weight=1)
        self._add_slider(settings, 0, "Silence threshold", self._threshold, -60.0, 0.0, "{:.0f} dB")
        self._add_slider(settings, 1, "Min silence", self._min_silence, 0.1, 3.0, "{:.2f} s")
        ttk.Label(settings, text="Padding").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Spinbox(settings, from_=0, to=1000, increment=10, width=8,
                    textvariable=self._padding).grid(row=2, column=1, sticky="w", padx=(12, 0))
        ttk.Label(settings, text="ms", style="Muted.TLabel").grid(row=2, column=2, sticky="w", padx=(6, 0))
        ttk.Label(settings, text="Audio track").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Combobox(settings, textvariable=self._audio_track, state="readonly", width=20,
                     values=list(_AUDIO_TRACK_CHOICES)).grid(row=3, column=1, columnspan=2,
                                                             sticky="w", padx=(12, 0))

        # Action.
        self._cut_btn = ttk.Button(body, text="Cut Timeline", style="Accent.TButton",
                                   command=self._on_cut, state="disabled")
        self._cut_btn.grid(row=row, column=0, sticky="ew", pady=(4, 8)); row += 1
        self._progress = ttk.Progressbar(body, mode="indeterminate")
        self._progress.grid(row=row, column=0, sticky="ew", pady=(0, 10)); row += 1

        # Log.
        self._section(body, row, "LOG"); row += 1
        log_wrap = tk.Frame(body, bg=C_INPUT, highlightthickness=0)
        log_wrap.grid(row=row, column=0, sticky="nsew", pady=(2, 0))
        body.rowconfigure(row, weight=1)
        log_wrap.columnconfigure(0, weight=1)
        log_wrap.rowconfigure(0, weight=1)
        self._log = tk.Text(log_wrap, height=7, wrap="word", state="disabled",
                            bg=C_INPUT, fg=C_MUTED, insertbackground=C_FG, relief="flat",
                            font=self.f_mono, padx=8, pady=6, highlightthickness=0,
                            selectbackground=C_ACCENT_DK)
        self._log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_wrap, command=self._log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self._log.configure(yscrollcommand=scroll.set)

    def _build_titlebar(self, parent) -> None:
        bar = tk.Frame(parent, bg=C_TITLE, height=40)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        canvas = tk.Canvas(bar, width=24, height=24, bg=C_TITLE, highlightthickness=0)
        canvas.pack(side="left", padx=(12, 8))
        self._draw_logo(canvas)

        title = tk.Label(bar, text="DaVinci AutoCut", bg=C_TITLE, fg=C_FG, font=self.f_title)
        title.pack(side="left")

        close = tk.Label(bar, text="✕", bg=C_TITLE, fg=C_MUTED, font=self.f_base,
                         padx=14, pady=2, cursor="hand2")
        close.pack(side="right", fill="y")
        close.bind("<Button-1>", lambda _e: self.root.destroy())
        close.bind("<Enter>", lambda _e: close.configure(fg=C_ERR))
        close.bind("<Leave>", lambda _e: close.configure(fg=C_MUTED))

        for widget in (bar, canvas, title):
            widget.bind("<Button-1>", self._start_move)
            widget.bind("<B1-Motion>", self._on_move)
        self.root.bind("<Escape>", lambda _e: self.root.destroy())

    def _draw_logo(self, c: tk.Canvas) -> None:
        # Mini version of the app icon: blue waveform bars + orange cut.
        for x, y0, y1 in [(2, 9, 16), (5, 5, 19), (8, 2, 22), (14, 2, 22), (17, 5, 19), (20, 9, 16)]:
            c.create_rectangle(x, y0, x + 2, y1, fill=C_ACCENT, outline="")
        c.create_line(10, 7, 14, 17, fill="#ff8a3d", width=2, capstyle="round")
        c.create_line(14, 7, 10, 17, fill="#ff8a3d", width=2, capstyle="round")

    def _section(self, parent, row, text) -> None:
        head = ttk.Frame(parent)
        head.grid(row=row, column=0, sticky="ew", pady=(6, 0))
        head.columnconfigure(1, weight=1)
        ttk.Label(head, text=text, style="Head.TLabel").grid(row=0, column=0, sticky="w")
        tk.Frame(head, bg="#33373f", height=1).grid(row=0, column=1, sticky="ew", padx=(10, 0))

    def _add_slider(self, parent, row, label, var, lo, hi, fmt) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        value_lbl = ttk.Label(parent, text=fmt.format(var.get()), style="Value.TLabel", width=7,
                              anchor="e")
        value_lbl.grid(row=row, column=2, sticky="e")
        scale = ttk.Scale(parent, from_=lo, to=hi, variable=var,
                          command=lambda _v, lbl=value_lbl, v=var, f=fmt: lbl.config(text=f.format(v.get())))
        scale.grid(row=row, column=1, sticky="ew", padx=(12, 8))

    # -- window move ---------------------------------------------------------

    def _start_move(self, e) -> None:
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _on_move(self, e) -> None:
        self.root.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    # -- event helpers (Tk thread) -------------------------------------------

    def _log_line(self, message: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", message + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _set_status(self, text: str, color: str) -> None:
        self._status.configure(text=text, foreground=color)

    # -- connect -------------------------------------------------------------

    def _on_connect(self) -> None:
        self._connect_btn.configure(state="disabled")
        self._set_status("Connecting...", C_MUTED)
        threading.Thread(target=self._connect_worker, daemon=True).start()

    def _connect_worker(self) -> None:
        try:
            conn = connect(self._resolve_obj)
            name = conn.current_timeline_name()
        except ResolveError as exc:
            self._events.put(("connect_error", str(exc)))
            return
        except Exception as exc:
            self._events.put(("connect_error", _format_unexpected(exc)))
            return
        self._events.put(("connect_ok", (conn, name)))

    # -- cut -----------------------------------------------------------------

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
            audio_track=_AUDIO_TRACK_CHOICES.get(self._audio_track.get(), "auto"),
        )
        self._log_line(
            f"Starting auto-cut (threshold {settings.silence_threshold_db:.0f} dB, "
            f"min silence {settings.min_silence_seconds:.2f}s, "
            f"padding {settings.padding_ms} ms, audio: {self._audio_track.get()})..."
        )
        threading.Thread(target=self._cut_worker, args=(settings,), daemon=True).start()

    def _cut_worker(self, settings: AnalysisSettings) -> None:
        def progress(message: str) -> None:
            self._events.put(("log", message))

        try:
            result = run_autocut(self._conn, settings, progress=progress)
        except (ResolveError, AudioAnalysisError) as exc:
            self._events.put(("cut_error", str(exc)))
            return
        except Exception as exc:  # pragma: no cover - last-resort guard
            self._events.put(("cut_error", _format_unexpected(exc)))
            return
        self._events.put(("cut_ok", result))

    # -- queue pump ----------------------------------------------------------

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self._events.get_nowait()
                self._handle_event(kind, payload)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _handle_event(self, kind: str, payload) -> None:
        if kind == "log":
            self._log_line(payload)
        elif kind == "connect_ok":
            self._conn, name = payload
            self._set_status("Connected", C_OK)
            self._log_line(f"Connected. Current timeline: {name!r}")
            self._connect_btn.configure(state="normal")
            self._cut_btn.configure(state="normal")
        elif kind == "connect_error":
            self._set_status("Not connected", C_ERR)
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


def _center(root, w, h) -> None:
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 3}")


def main(resolve_obj=None) -> None:
    """Launch the GUI. ``resolve_obj`` is Resolve's injected ``resolve`` global."""
    root = tk.Tk()
    root.title("DaVinci AutoCut")
    try:
        root.overrideredirect(True)  # borderless; our title bar replaces the OS chrome
    except tk.TclError:
        pass
    _center(root, 440, 560)
    AutoCutApp(root, resolve_obj=resolve_obj)
    root.lift()
    root.attributes("-topmost", True)
    root.after(600, lambda: root.attributes("-topmost", False))
    root.focus_force()
    root.mainloop()


if __name__ == "__main__":
    main()
