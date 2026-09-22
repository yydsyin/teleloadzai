"""Teleloadzai.

Importing the package puts our own package folder on the import path, so
anything we pip-install lands inside `bin/pylibs` and never in the user's
Python (decision 27). Without this line the only place a package like
pywebview could live was the user's own installation -- which is exactly
where it was found on 2026-09-22.
"""

import sys as _sys

from .paths import BIN_DIR as _BIN_DIR

_LIBS = str(_BIN_DIR / "pylibs")
if _LIBS not in _sys.path:
    _sys.path.insert(0, _LIBS)

from .config import APP_NAME, APP_SLUG, APP_VERSION

__all__ = ["APP_NAME", "APP_SLUG", "APP_VERSION"]
