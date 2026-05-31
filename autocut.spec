# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: build a standalone DaVinci Auto-Cut executable.

Any ffmpeg/ffprobe binaries placed in a ``vendor/`` folder next to this spec are
bundled into the executable, so the resulting app needs no separate ffmpeg
install. The build scripts download them there automatically.

Build with:  pyinstaller autocut.spec
"""

import os

block_cipher = None

# Collect bundled ffmpeg binaries (if the build placed them in vendor/).
_vendor = os.path.join(os.getcwd(), "vendor")
binaries = []
for _name in ("ffmpeg.exe", "ffprobe.exe", "ffmpeg", "ffprobe"):
    _path = os.path.join(_vendor, _name)
    if os.path.isfile(_path):
        binaries.append((_path, "."))  # extract next to the app at runtime

a = Analysis(
    ["autocut.py"],
    pathex=[],
    binaries=binaries,
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="DaVinciAutoCut",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI app: no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
