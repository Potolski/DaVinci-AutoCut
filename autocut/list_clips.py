"""Manual smoke test: connect to Resolve and print the current timeline's clips.

Run it with Resolve open and a timeline loaded:

    python -m autocut.list_clips

This exercises only the connection + reading path, so you can confirm the
scripting bridge works before touching audio analysis or timeline building.
"""

from __future__ import annotations

import sys

from .resolve_api import ResolveError, connect


def main() -> int:
    try:
        conn = connect()
        print(f"Connected. Current timeline: {conn.current_timeline_name()!r}")
        clips = conn.read_timeline_clips()
    except ResolveError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not clips:
        print("No source-backed video clips found on the timeline.")
        return 0

    print(f"Found {len(clips)} clip(s):\n")
    for i, clip in enumerate(clips, 1):
        print(
            f"  [{i}] {clip.name}\n"
            f"      file:   {clip.file_path}\n"
            f"      source: frames {clip.source_start_frame}-{clip.source_end_frame} "
            f"@ {clip.fps:g} fps (track V{clip.track_index})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
