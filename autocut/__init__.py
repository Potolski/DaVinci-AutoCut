"""DaVinci Resolve Auto-Cut.

A standalone tool that removes silent gaps from a DaVinci Resolve timeline by
analyzing the source audio with ffmpeg + pydub and building a fresh cut timeline
that references the original media. The original timeline is never modified.
"""

__version__ = "0.1.0"
