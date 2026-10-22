"""Legacy alias for the current checkout's canonical package module.

Only source-checkout callers bootstrap integrations/python. Installed package
modules never import experiments or change sys.path to locate them.
"""
import importlib as _importlib
import sys as _sys
from pathlib import Path as _Path

_package_root = _Path(__file__).resolve().parents[2] / "integrations/python"
_expected = _package_root / "moontxnwitness_capture"
_loaded = _sys.modules.get("moontxnwitness_capture")
if (_expected / "__init__.py").is_file():
    if _loaded is None:
        # Prefer this checkout over an older, as-yet-unloaded installed package.
        _value = str(_package_root)
        _sys.path[:] = [_value] + [value for value in _sys.path if value != _value]
    else:
        _file = getattr(_loaded, "__file__", None)
        if not _file or _Path(_file).resolve().parent != _expected.resolve():
            raise ImportError("moontxnwitness_capture is already loaded from another source context; use a fresh process with this checkout's integrations/python")
try:
    _implementation = _importlib.import_module("moontxnwitness_capture._initialization_guard")
except ModuleNotFoundError as _error:
    raise ImportError("The selected moontxnwitness_capture installation lacks the legacy target _initialization_guard; no package is reloaded automatically") from _error

# A module-object alias preserves legacy monkeypatches of implementation globals.
_sys.modules[__name__] = _implementation
