#!/usr/bin/env python3
"""Render the logo assets from the SVG sources.

Produces, next to the SVGs:
  * icon.png  (512) and icon-256.png  -- the app-icon mark
  * logo.png  (1100x300)              -- the README banner
  * icon.ico  (multi-size)            -- the Windows installer icon

Requires: pip install pillow cairosvg
Run:      python assets/build_assets.py
"""

import io
import os

import cairosvg
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))


def _png_bytes(svg_path, **kw):
    return cairosvg.svg2png(url=svg_path, **kw)


def _save_png(svg_name, out_name, **kw):
    data = _png_bytes(os.path.join(HERE, svg_name), **kw)
    with open(os.path.join(HERE, out_name), "wb") as handle:
        handle.write(data)
    return data


def main():
    # README banner.
    _save_png("logo.svg", "logo.png", output_width=1100, output_height=300)

    # App-icon PNGs.
    _save_png("icon.svg", "icon.png", output_width=512, output_height=512)
    icon_256 = _save_png("icon.svg", "icon-256.png", output_width=256, output_height=256)

    # Multi-size Windows .ico from the 256px render.
    base = Image.open(io.BytesIO(icon_256)).convert("RGBA")
    base.save(
        os.path.join(HERE, "icon.ico"),
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("Wrote logo.png, icon.png, icon-256.png, icon.ico")


if __name__ == "__main__":
    main()
