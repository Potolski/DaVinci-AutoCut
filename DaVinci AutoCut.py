#!/usr/bin/env python
"""DaVinci AutoCut -- launcher for the Workspace -> Scripts menu.

DaVinci Resolve runs this file when you pick it from
``Workspace -> Scripts -> DaVinci AutoCut``. When launched that way, Resolve
injects ``resolve`` (plus ``fusion``, ``bmd`` and ``app``) into this script's
globals -- and those work in the FREE version, unlike an external connection.

The file name (with the space) is what shows up as the menu label, so keep it.
This launcher lives next to the ``autocut`` package; the installer copies both
into Resolve's Scripts folder.

Any error here is written to ``davinci-autocut-startup.log`` next to this file
AND printed to Resolve's Console, so a failure is never silent.
"""

import os
import sys
import traceback


def _plugin_dir():
    """Folder containing this launcher (and the ``autocut`` package)."""
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        # Some embedded runners don't define __file__.
        return os.getcwd()


def _log_startup_error(text):
    try:
        path = os.path.join(_plugin_dir(), "davinci-autocut-startup.log")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError:
        pass


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
    sys.path.insert(0, _plugin_dir())
    from autocut.gui import main

    main(resolve_obj=_get_resolve())


try:
    run()
except Exception:
    tb = traceback.format_exc()
    _log_startup_error(tb)
    print("DaVinci AutoCut failed to start:\n" + tb)
    raise
