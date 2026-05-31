"""Set up the DaVinci Resolve scripting environment.

Blackmagic's Python API needs three things before ``DaVinciResolveScript`` can be
imported:

* ``RESOLVE_SCRIPT_API``  – the Developer/Scripting folder
* ``RESOLVE_SCRIPT_LIB``  – the native ``fusionscript`` shared library
* the ``Modules`` folder on ``sys.path`` / ``PYTHONPATH``

We configure these internally from the standard install locations so the user
never has to touch their shell profile. Call :func:`load_resolve_module` to get
the imported module back.
"""

from __future__ import annotations

import os
import sys

# Standard install locations per platform. The first existing entry wins, so we
# can tolerate minor version/layout differences between Resolve releases.
_DEFAULT_PATHS = {
    "darwin": {
        "api": "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting",
        "lib": "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so",
    },
    "win32": {
        "api": os.path.expandvars(
            r"%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
        ),
        "lib": r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll",
    },
    "linux": {
        "api": "/opt/resolve/Developer/Scripting",
        "lib": "/opt/resolve/libs/Fusion/fusionscript.so",
    },
}


class ResolveEnvironmentError(RuntimeError):
    """Raised when the Resolve scripting modules cannot be located or imported."""


def _platform_key() -> str:
    if sys.platform.startswith("win"):
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def configure_environment() -> None:
    """Populate the Resolve scripting environment variables in-process.

    Respects values the user has already exported; only fills in the gaps from
    the platform defaults. Safe to call more than once.
    """
    defaults = _DEFAULT_PATHS[_platform_key()]

    api_path = os.environ.get("RESOLVE_SCRIPT_API", defaults["api"])
    lib_path = os.environ.get("RESOLVE_SCRIPT_LIB", defaults["lib"])

    os.environ["RESOLVE_SCRIPT_API"] = api_path
    os.environ["RESOLVE_SCRIPT_LIB"] = lib_path

    modules_path = os.path.join(api_path, "Modules")
    if modules_path not in sys.path:
        sys.path.append(modules_path)

    # Keep PYTHONPATH in sync for any child processes / re-imports.
    existing = os.environ.get("PYTHONPATH", "")
    if modules_path not in existing.split(os.pathsep):
        os.environ["PYTHONPATH"] = (
            os.pathsep.join([existing, modules_path]) if existing else modules_path
        )


def load_resolve_module():
    """Configure the environment and import Blackmagic's scripting module.

    Returns the imported ``DaVinciResolveScript`` module. Raises
    :class:`ResolveEnvironmentError` with an actionable message if it cannot be
    found (Resolve not installed, or installed in a non-standard location).
    """
    configure_environment()

    api_path = os.environ.get("RESOLVE_SCRIPT_API", "<unset>")
    lib_path = os.environ.get("RESOLVE_SCRIPT_LIB", "<unset>")

    try:
        # Catch broadly: Blackmagic's module can fail in surprising ways
        # (missing native lib, the removed stdlib 'imp' module, etc.), not just
        # with a plain ImportError.
        import DaVinciResolveScript as dvr_script  # type: ignore
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        lines = [
            "Could not load the DaVinci Resolve scripting module.",
            f"Reason: {detail}",
            f"Modules path: {os.path.join(api_path, 'Modules')}",
            f"Library (RESOLVE_SCRIPT_LIB): {lib_path}",
        ]

        if lib_path not in ("<unset>", "") and not os.path.isfile(lib_path):
            lines.append(
                "-> That fusionscript library file does not exist. DaVinci "
                "Resolve may be installed in a non-standard location; set the "
                "RESOLVE_SCRIPT_LIB environment variable to its real path."
            )

        # Blackmagic's DaVinciResolveScript.py uses the legacy 'imp' module,
        # which Python removed in 3.12. A build on 3.12+ will hit this.
        if isinstance(exc, ModuleNotFoundError) and getattr(exc, "name", "") == "imp":
            lines.append(
                "-> This app was built with a Python version (3.12+) that "
                "removed the legacy 'imp' module that Resolve's scripting "
                "module relies on. Please use the build made with Python 3.11."
            )

        lines.append(
            "Also confirm Resolve is running and scripting is set to Local "
            "(Preferences -> System -> General -> External scripting using)."
        )
        raise ResolveEnvironmentError("\n".join(lines)) from exc

    return dvr_script
