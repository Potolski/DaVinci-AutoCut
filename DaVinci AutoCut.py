#!/usr/bin/env python
"""DaVinci AutoCut -- launcher for the Workspace -> Scripts menu.

DaVinci Resolve runs this file when you pick it from
``Workspace -> Scripts -> DaVinci AutoCut``. When launched that way, Resolve
injects ``resolve`` (plus ``fusion``, ``bmd`` and ``app``) into this script's
globals -- and those work in the FREE version, unlike an external connection.

The file name (with the space) is what shows up as the menu label, so keep it.
This launcher lives next to the ``autocut`` package; the installer copies both
into Resolve's Scripts folder.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _get_resolve():
    """Return Resolve's injected scripting object, or None if not available."""
    injected = globals()
    if injected.get("resolve") is not None:
        return injected["resolve"]

    # Free-version fallback: the injected Fusion 'app' can hand back Resolve.
    app_obj = injected.get("app")
    if app_obj is not None:
        try:
            return app_obj.GetResolve()
        except Exception:
            pass
    return None


def run():
    from autocut.gui import main

    main(resolve_obj=_get_resolve())


run()
