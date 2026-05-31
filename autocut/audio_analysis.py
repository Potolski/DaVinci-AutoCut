"""Find the non-silent ("keep") regions of an audio file using ffmpeg.

Silence detection is done entirely by ffmpeg's built-in ``silencedetect`` audio
filter, parsed from its stderr output. This means the only external dependency
is ffmpeg itself -- there are no Python packages to install into Resolve's
interpreter, which matters because the plugin runs inside DaVinci Resolve.

ffmpeg is located by absolute path (a copy shipped next to the plugin, or one on
PATH), so the user never has to configure their PATH.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional, Tuple


class AudioAnalysisError(RuntimeError):
    """A problem locating ffmpeg or analyzing a source audio file."""


@dataclass(frozen=True)
class AnalysisSettings:
    """Tunable parameters for silence detection.

    * ``silence_threshold_db`` -- levels below this (dBFS) count as silent.
    * ``min_silence_seconds``  -- only silences at least this long are cut.
    * ``padding_ms``           -- breathing room kept on each side of a segment.
    """

    silence_threshold_db: float = -40.0
    min_silence_seconds: float = 0.5
    padding_ms: int = 150


# -- locating ffmpeg ---------------------------------------------------------


def _candidate_dirs() -> List[str]:
    """Directories that may hold a bundled ffmpeg, most-specific first."""
    here = os.path.dirname(os.path.abspath(__file__))
    dirs = [
        os.path.join(here, "bin"),  # installed: autocut/bin/ffmpeg.exe
        here,
        os.path.dirname(here),  # the plugin folder itself
    ]
    if getattr(sys, "frozen", False):  # also support a PyInstaller build
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            dirs.append(meipass)
        dirs.append(os.path.dirname(sys.executable))
    return dirs


def _find_ffmpeg() -> Optional[str]:
    """Return a path to ffmpeg: a bundled copy if present, else one on PATH."""
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    for directory in _candidate_dirs():
        candidate = os.path.join(directory, exe)
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("ffmpeg")


def ensure_ffmpeg_available() -> str:
    """Return a usable ffmpeg path or raise :class:`AudioAnalysisError`."""
    ffmpeg = _find_ffmpeg()
    if ffmpeg is None:
        raise AudioAnalysisError(
            "ffmpeg could not be found. The installer normally places it next "
            "to the plugin; if you installed manually, put ffmpeg(.exe) in the "
            "plugin's 'bin' folder or on your PATH."
        )
    return ffmpeg


def _no_window_kwargs() -> dict:
    """Keep a console window from flashing when ffmpeg runs under a GUI on Windows."""
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return {"startupinfo": startupinfo, "creationflags": creationflags}


# -- silence detection -------------------------------------------------------

_SILENCE_START = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
_SILENCE_END = re.compile(r"silence_end:\s*(-?\d+(?:\.\d+)?)")


def parse_silences(stderr_text: str) -> List[Tuple[float, float]]:
    """Parse ffmpeg ``silencedetect`` stderr into (start_ms, end_ms) intervals.

    A trailing ``silence_start`` with no matching ``silence_end`` (the file ends
    mid-silence) is reported as running to infinity; callers clamp it to the
    region of interest.
    """
    silences: List[Tuple[float, float]] = []
    pending: Optional[float] = None
    for line in stderr_text.splitlines():
        start = _SILENCE_START.search(line)
        if start:
            pending = max(0.0, float(start.group(1)))
            continue
        end = _SILENCE_END.search(line)
        if end and pending is not None:
            silences.append((pending * 1000.0, float(end.group(1)) * 1000.0))
            pending = None
    if pending is not None:
        silences.append((pending * 1000.0, float("inf")))
    return silences


@lru_cache(maxsize=64)
def _detect_file_silences(
    file_path: str, threshold_db: float, min_silence_seconds: float
) -> Tuple[Tuple[float, float], ...]:
    """Run ffmpeg once per (file, settings) and return silence intervals in ms."""
    ffmpeg = ensure_ffmpeg_available()
    audio_filter = f"silencedetect=noise={threshold_db}dB:d={min_silence_seconds}"
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostats", "-i", file_path,
             "-af", audio_filter, "-f", "null", "-"],
            capture_output=True,
            text=True,
            **_no_window_kwargs(),
        )
    except OSError as exc:
        raise AudioAnalysisError(f"Could not run ffmpeg: {exc}") from exc

    silences = parse_silences(proc.stderr)
    # silencedetect emits its findings even on success; a non-zero exit with no
    # findings means ffmpeg couldn't read the file at all.
    if proc.returncode != 0 and not silences:
        tail = "\n".join(proc.stderr.strip().splitlines()[-3:])
        raise AudioAnalysisError(
            f"ffmpeg failed to read {os.path.basename(file_path)}:\n{tail}"
        )
    return tuple(silences)


def find_keep_ranges_ms(
    file_path: str,
    region_start_ms: float,
    region_end_ms: float,
    settings: AnalysisSettings,
) -> List[Tuple[float, float]]:
    """Return non-silent ranges (absolute source ms) within a clip's region.

    The complement of the detected silences inside
    ``[region_start_ms, region_end_ms)`` gives the kept segments; each is then
    padded outward, clamped to the region, and overlapping segments are merged.
    """
    start = max(0.0, region_start_ms)
    end = region_end_ms
    if end <= start:
        return []

    silences = _detect_file_silences(
        file_path, settings.silence_threshold_db, settings.min_silence_seconds
    )

    segments: List[Tuple[float, float]] = []
    cursor = start
    for sil_start, sil_end in silences:
        if sil_end <= start or sil_start >= end:
            continue
        sil_start = max(sil_start, start)
        sil_end = min(sil_end, end)
        if sil_start > cursor:
            segments.append((cursor, sil_start))
        cursor = max(cursor, sil_end)
    if cursor < end:
        segments.append((cursor, end))

    pad = settings.padding_ms
    padded = [(max(start, a - pad), min(end, b + pad)) for a, b in segments]
    return _merge_overlapping(padded)


def _merge_overlapping(ranges: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Merge ranges that overlap or touch after padding has been applied."""
    if not ranges:
        return []
    ranges = sorted(ranges)
    merged = [ranges[0]]
    for start, end in ranges[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged
