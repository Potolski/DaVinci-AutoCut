#!/usr/bin/env python
"""DaVinci AutoCut -- launcher for the Workspace -> Scripts menu.

DaVinci Resolve runs this file when you pick it from
``Workspace -> Scripts -> DaVinci AutoCut``. When launched that way, Resolve
injects ``resolve`` (plus ``fusion``, ``bmd`` and ``app``) into this script's
globals -- and those work in the FREE version, unlike an external connection.

The file name (with the space) is what shows up as the menu label, so keep it.
This launcher lives next to the ``autocut`` package; the installer copies both
into Resolve's Scripts folder.

NOTE: Resolve does NOT define ``__file__`` for menu scripts, so we locate the
``autocut`` package by checking ``sys.argv[0]`` and the standard install
folders rather than relying on ``__file__``. Any startup error is written to
``davinci-autocut-startup.log`` and printed to Resolve's Console.
"""

import os
import sys
import traceback


def _standard_install_dirs():
    """Folders DaVinci AutoCut is normally installed into, per platform."""
    home = os.path.expanduser("~")
    bases = []

    appdata = os.environ.get("APPDATA")
    if appdata:  # Windows
        bases.append(os.path.join(appdata, "Blackmagic Design", "DaVinci Resolve",
                                  "Support", "Fusion", "Scripts", "Edit"))
    # macOS
    bases.append(os.path.join(home, "Library", "Application Support", "Blackmagic Design",
                              "DaVinci Resolve", "Fusion", "Scripts", "Edit"))
    bases.append(os.path.join(home, "Library", "Application Support", "Blackmagic Design",
                              "DaVinci Resolve", "Support", "Fusion", "Scripts", "Edit"))
    # Linux
    bases.append(os.path.join(home, ".local", "share", "DaVinciResolve",
                              "Fusion", "Scripts", "Edit"))

    dirs = []
    for base in bases:
        dirs.append(os.path.join(base, "DaVinciAutoCut"))  # installer layout
        dirs.append(base)  # manual install (files dropped straight into Edit/)
    return dirs


def _candidate_dirs():
    cands = []
    try:  # only if some runner does define __file__
        cands.append(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    if sys.argv and sys.argv[0]:
        cands.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    cands.extend(_standard_install_dirs())
    return cands


def _find_plugin_dir():
    """Return the folder containing the ``autocut`` package, or None."""
    for directory in _candidate_dirs():
        if directory and os.path.isfile(os.path.join(directory, "autocut", "__init__.py")):
            return directory
    return None


def _log_startup_error(text, plugin_dir):
    for target in (plugin_dir, os.path.expanduser("~")):
        if not target:
            continue
        try:
            with open(os.path.join(target, "davinci-autocut-startup.log"),
                      "w", encoding="utf-8") as handle:
                handle.write(text)
            return
        except OSError:
            continue


def _get_resolve():
    """Return Resolve's injected scripting object, or None if not available."""
    injected = globals()
    if injected.get("resolve") is not None:
        return injected["resolve"]

    app_obj = injected.get("app")  # free-version fallback
    if app_obj is not None:
        try:
            return app_obj.GetResolve()
        except Exception:
            pass
    return None


def run():
    plugin_dir = _find_plugin_dir()
    if plugin_dir is None:
        raise RuntimeError(
            "Could not find the 'autocut' package. Reinstall DaVinci AutoCut so "
            "that 'DaVinci AutoCut.py' and the 'autocut' folder sit together in "
            "Resolve's Scripts/Edit folder."
        )
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)

    from autocut.gui import main

    main(resolve_obj=_get_resolve())
    return plugin_dir


try:
    run()
except Exception:
    tb = traceback.format_exc()
    _log_startup_error(tb, _find_plugin_dir())
    print("DaVinci AutoCut failed to start:\n" + tb)
    raise
