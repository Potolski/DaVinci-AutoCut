"""Talk to a running DaVinci Resolve instance.

This module wraps Blackmagic's scripting objects (Resolve / Project /
MediaPool / Timeline / TimelineItem) behind a small, typed-ish surface:

* :func:`connect` – attach to the running app and return a :class:`ResolveConnection`.
* :meth:`ResolveConnection.read_timeline_clips` – list the clips on the current
  timeline with their source media paths and source in/out points.
* :meth:`ResolveConnection.build_cut_timeline` – append keep-range subclips to a
  brand-new timeline (the original is left untouched).

All Resolve-specific failure modes are surfaced as :class:`ResolveError` with a
human-readable message.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .resolve_env import ResolveEnvironmentError, load_resolve_module


class ResolveError(RuntimeError):
    """A user-facing problem talking to DaVinci Resolve."""


@dataclass
class TimelineClip:
    """A single clip on the source timeline.

    Frame numbers are in the *source media's* frame space (what Resolve's
    ``AppendToTimeline`` expects for ``startFrame``/``endFrame``).
    """

    name: str
    file_path: str
    source_start_frame: int
    source_end_frame: int
    fps: float
    media_pool_item: object  # Blackmagic MediaPoolItem (opaque)
    track_index: int

    @property
    def source_start_ms(self) -> float:
        return self.source_start_frame / self.fps * 1000.0

    @property
    def source_end_ms(self) -> float:
        # GetSourceEndFrame is inclusive; add one frame for an exclusive end.
        return (self.source_end_frame + 1) / self.fps * 1000.0


@dataclass
class KeepRange:
    """A non-silent region to keep, expressed in source frames."""

    media_pool_item: object
    start_frame: int
    end_frame: int


def connect(resolve_obj=None) -> "ResolveConnection":
    """Return a connection wrapper around the Resolve scripting object.

    The plugin launcher passes ``resolve_obj`` -- the ``resolve`` global that
    DaVinci Resolve injects into scripts run from ``Workspace -> Scripts``. That
    injected object works in the FREE version. If it isn't supplied we fall back
    to the external ``scriptapp`` connection, which only works in Studio.

    Raises :class:`ResolveError` with guidance if no object can be obtained.
    """
    resolve = resolve_obj or _connect_external()
    if resolve is None:
        raise ResolveError(
            "Could not obtain the DaVinci Resolve scripting object.\n"
            "The free version only exposes scripting to scripts launched from\n"
            "inside Resolve. Run this from Workspace -> Scripts -> DaVinci AutoCut\n"
            "(not as a standalone app). Also make sure a project is open."
        )
    return ResolveConnection(resolve)


def _connect_external():
    """Best-effort external connection (Studio only). Returns None on failure."""
    try:
        dvr_script = load_resolve_module()
    except ResolveEnvironmentError:
        return None
    try:
        return dvr_script.scriptapp("Resolve")
    except Exception:
        return None


class ResolveConnection:
    """Thin wrapper around the Resolve scripting object graph."""

    def __init__(self, resolve):
        self._resolve = resolve

    # -- project / timeline lookup ------------------------------------------

    def _project(self):
        pm = self._resolve.GetProjectManager()
        project = pm.GetCurrentProject() if pm else None
        if project is None:
            raise ResolveError("No project is open in DaVinci Resolve.")
        return project

    def _current_timeline(self):
        project = self._project()
        timeline = project.GetCurrentTimeline()
        if timeline is None:
            raise ResolveError(
                "No timeline is open. Open the timeline you want to cut in "
                "DaVinci Resolve first."
            )
        return timeline

    def current_timeline_name(self) -> str:
        return self._current_timeline().GetName()

    # -- reading --------------------------------------------------------------

    def read_timeline_clips(self) -> List[TimelineClip]:
        """Return every video clip on the current timeline.

        Clips without a backing media-pool item (e.g. generators, titles,
        compound clips with no single source file) are skipped.
        """
        timeline = self._current_timeline()
        timeline_fps = _safe_float(timeline.GetSetting("timelineFrameRate"))

        clips: List[TimelineClip] = []
        track_count = int(timeline.GetTrackCount("video") or 0)
        for track_index in range(1, track_count + 1):
            items = timeline.GetItemListInTrack("video", track_index) or []
            for item in items:
                clip = self._item_to_clip(item, track_index, timeline_fps)
                if clip is not None:
                    clips.append(clip)
        return clips

    def _item_to_clip(self, item, track_index: int, timeline_fps: float) -> Optional[TimelineClip]:
        media_pool_item = item.GetMediaPoolItem()
        if media_pool_item is None:
            return None

        file_path = media_pool_item.GetClipProperty("File Path") or ""
        if not file_path:
            # No source file on disk (title/generator/etc.) -> nothing to analyze.
            return None

        fps = _clip_fps(media_pool_item, timeline_fps)

        return TimelineClip(
            name=item.GetName() or media_pool_item.GetName() or "clip",
            file_path=file_path,
            source_start_frame=int(item.GetSourceStartFrame()),
            source_end_frame=int(item.GetSourceEndFrame()),
            fps=fps,
            media_pool_item=media_pool_item,
            track_index=track_index,
        )

    # -- writing --------------------------------------------------------------

    def build_cut_timeline(self, keep_ranges: List[KeepRange], name: str) -> str:
        """Create a new timeline and append every keep-range as a subclip.

        Returns the name of the created timeline. The source timeline is never
        modified. Uses ``MediaPool.AppendToTimeline`` with explicit source
        in/out frames, which is far more reliable than in-place blade/ripple.
        """
        if not keep_ranges:
            raise ResolveError("Nothing to keep – every analyzed clip was silent.")

        project = self._project()
        media_pool = project.GetMediaPool()

        new_timeline = media_pool.CreateEmptyTimeline(name)
        if new_timeline is None:
            raise ResolveError(f"Resolve refused to create a timeline named {name!r}.")

        # Make the new timeline current so AppendToTimeline targets it.
        project.SetCurrentTimeline(new_timeline)

        clip_infos = [
            {
                "mediaPoolItem": kr.media_pool_item,
                "startFrame": kr.start_frame,
                "endFrame": kr.end_frame,
            }
            for kr in keep_ranges
        ]

        appended = media_pool.AppendToTimeline(clip_infos)
        if not appended:
            raise ResolveError(
                "AppendToTimeline returned nothing – no subclips were added. "
                "The keep-ranges may be out of the media's bounds."
            )

        return new_timeline.GetName()


def _safe_float(value, default: float = 24.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clip_fps(media_pool_item, timeline_fps: float) -> float:
    """Best-effort source frame rate, falling back to the timeline rate."""
    fps = _safe_float(media_pool_item.GetClipProperty("FPS"), default=0.0)
    return fps if fps > 0 else timeline_fps
