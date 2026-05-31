"""Orchestrate the full auto-cut: read clips, analyze audio, build a new timeline.

This is the glue between :mod:`autocut.resolve_api` and
:mod:`autocut.audio_analysis`. It converts the millisecond keep-ranges from the
analyzer into source-frame subclips and hands them to Resolve, leaving the
original timeline untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List

from .audio_analysis import (
    AnalysisSettings,
    AudioAnalysisError,
    ensure_ffmpeg_available,
    find_keep_ranges_ms,
)
from .resolve_api import KeepRange, ResolveConnection, ResolveError, TimelineClip

# Progress is reported as a short human-readable status line.
ProgressCallback = Callable[[str], None]


@dataclass
class CutResult:
    """Summary of an auto-cut run."""

    new_timeline_name: str
    clips_analyzed: int
    segments_kept: int
    skipped_clips: List[str] = field(default_factory=list)


def _noop(_message: str) -> None:
    pass


def ms_range_to_frames(start_ms: float, end_ms: float, fps: float) -> tuple[int, int]:
    """Convert an exclusive-end millisecond range to an inclusive frame range.

    Resolve's ``AppendToTimeline`` treats ``endFrame`` as inclusive, so we round
    the exclusive end to a frame and step back one.
    """
    start_frame = round(start_ms / 1000.0 * fps)
    end_frame = round(end_ms / 1000.0 * fps) - 1
    return start_frame, end_frame


def _clip_to_keep_ranges(clip: TimelineClip, settings: AnalysisSettings) -> List[KeepRange]:
    ms_ranges = find_keep_ranges_ms(
        clip.file_path,
        clip.source_start_ms,
        clip.source_end_ms,
        settings,
    )

    keep_ranges: List[KeepRange] = []
    for start_ms, end_ms in ms_ranges:
        start_frame, end_frame = ms_range_to_frames(start_ms, end_ms, clip.fps)
        # Stay within the frames this clip actually references on the timeline.
        start_frame = max(start_frame, clip.source_start_frame)
        end_frame = min(end_frame, clip.source_end_frame)
        if end_frame < start_frame:
            continue
        keep_ranges.append(
            KeepRange(
                media_pool_item=clip.media_pool_item,
                start_frame=start_frame,
                end_frame=end_frame,
            )
        )
    return keep_ranges


def run_autocut(
    conn: ResolveConnection,
    settings: AnalysisSettings,
    progress: ProgressCallback = _noop,
    new_timeline_suffix: str = "AutoCut",
) -> CutResult:
    """Analyze the current timeline and build a silence-trimmed copy.

    Raises :class:`ResolveError` or :class:`AudioAnalysisError` on failure.
    """
    ensure_ffmpeg_available()

    source_name = conn.current_timeline_name()
    progress(f"Reading clips from {source_name!r}...")
    clips = conn.read_timeline_clips()
    if not clips:
        raise ResolveError("No source-backed video clips found on the timeline.")

    # Capture this before we create/switch to the new timeline.
    audio_track_count = conn.source_audio_track_count()

    all_keep_ranges: List[KeepRange] = []
    skipped: List[str] = []

    for index, clip in enumerate(clips, 1):
        progress(f"Analyzing clip {index}/{len(clips)}: {clip.name}")
        try:
            ranges = _clip_to_keep_ranges(clip, settings)
        except AudioAnalysisError as exc:
            # One unreadable clip shouldn't abort the whole run.
            progress(f"  Skipped {clip.name}: {exc}")
            skipped.append(clip.name)
            continue
        if not ranges:
            skipped.append(clip.name)
        all_keep_ranges.extend(ranges)

    if not all_keep_ranges:
        raise ResolveError(
            "Every analyzed clip was silent under the current settings. "
            "Try a lower (more negative) dB threshold."
        )

    new_name = f"{source_name} - {new_timeline_suffix}"
    progress(f"Building new timeline {new_name!r} with {len(all_keep_ranges)} segment(s)...")
    created_name = conn.build_cut_timeline(
        all_keep_ranges, new_name, audio_track_count=audio_track_count
    )

    return CutResult(
        new_timeline_name=created_name,
        clips_analyzed=len(clips),
        segments_kept=len(all_keep_ranges),
        skipped_clips=skipped,
    )
