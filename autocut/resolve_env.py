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

    try:
        import DaVinciResolveScript as dvr_script  # type: ignore
    except ImportError as exc:
        api_path = os.environ.get("RESOLVE_SCRIPT_API", "<unset>")
        raise ResolveEnvironmentError(
            "Could not import the DaVinci Resolve scripting module.\n"
            f"Looked under: {os.path.join(api_path, 'Modules')}\n"
            "Make sure DaVinci Resolve is installed. If it lives in a custom "
            "location, set the RESOLVE_SCRIPT_API and RESOLVE_SCRIPT_LIB "
            "environment variables before launching."
        ) from exc

    return dvr_script
