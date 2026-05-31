"""Find the non-silent ("keep") regions of an audio file with ffmpeg + pydub.

Everything here works directly on the source media on disk – we never pull
samples through the Resolve API. ffmpeg must be installed and on PATH; pydub
shells out to it to decode whatever container/codec the source uses.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Tuple

from pydub import AudioSegment
from pydub.silence import detect_nonsilent


class AudioAnalysisError(RuntimeError):
    """A problem decoding or analyzing a source audio file."""


@dataclass(frozen=True)
class AnalysisSettings:
    """Tunable parameters for silence detection.

    * ``silence_threshold_db`` – levels below this (dBFS) count as silent.
    * ``min_silence_seconds``  – only silences at least this long are cut.
    * ``padding_ms``           – breathing room kept on each side of a segment.
    """

    silence_threshold_db: float = -40.0
    min_silence_seconds: float = 0.5
    padding_ms: int = 150


def ensure_ffmpeg_available() -> None:
    """Raise :class:`AudioAnalysisError` if ffmpeg is not on PATH."""
    if shutil.which("ffmpeg") is None:
        raise AudioAnalysisError(
            "ffmpeg was not found on your PATH. Install it and try again:\n"
            "  macOS:   brew install ffmpeg\n"
            "  Windows: download from https://www.gyan.dev/ffmpeg/builds/ "
            "and add its bin/ folder to PATH."
        )


@lru_cache(maxsize=32)
def _load_audio(file_path: str) -> AudioSegment:
    """Decode a file to a mono :class:`AudioSegment` (cached per path)."""
    try:
        audio = AudioSegment.from_file(file_path)
    except Exception as exc:  # pydub raises a grab-bag of exception types
        raise AudioAnalysisError(
            f"Could not decode audio from {file_path!r}: {exc}"
        ) from exc
    # Mono keeps level math simple and matches how speech sits in the mix.
    return audio.set_channels(1)


def find_keep_ranges_ms(
    file_path: str,
    region_start_ms: float,
    region_end_ms: float,
    settings: AnalysisSettings,
) -> List[Tuple[float, float]]:
    """Return non-silent ranges (in absolute source ms) within a clip's region.

    Only the ``[region_start_ms, region_end_ms)`` slice of the source is
    analyzed – that is the portion the timeline clip actually uses. Padding is
    applied to each kept segment and overlapping segments are merged. Returned
    ranges are clamped to the region.
    """
    audio = _load_audio(file_path)

    start = max(0, int(region_start_ms))
    end = min(len(audio), int(region_end_ms))
    if end <= start:
        return []

    region = audio[start:end]

    nonsilent = detect_nonsilent(
        region,
        min_silence_len=max(1, int(settings.min_silence_seconds * 1000)),
        silence_thresh=settings.silence_threshold_db,
        seek_step=1,
    )
    if not nonsilent:
        return []

    # Offset back to absolute source coordinates and apply padding.
    padded: List[Tuple[float, float]] = []
    for seg_start, seg_end in nonsilent:
        abs_start = start + seg_start - settings.padding_ms
        abs_end = start + seg_end + settings.padding_ms
        abs_start = max(start, abs_start)
        abs_end = min(end, abs_end)
        padded.append((abs_start, abs_end))

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
