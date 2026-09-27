"""little-sister check type: ``wiz``.

Importing this package registers the type in little-sister's ``CHECK_TYPES``. A
deployment therefore needs one line in its ``wsgi.py``, before it imports
``little_sister.app``::

    import little_sister_wiz              # noqa: F401  registers its type
    from little_sister.app import app     # the app; its start builds the engine

``require_api`` declares the **check API epoch** this package was built for. It
refuses at startup, naming both epochs, when the library has moved past the
surface below — the upgrade an install-time floor cannot see, because a floor has
no ceiling (little-sister ADR-0051). Without it the same mismatch would surface as
an ``ImportError`` from inside this package, which reads like our bug.
"""
from importlib.metadata import PackageNotFoundError, version

from little_sister.checks import require_api

require_api(3)

from little_sister_wiz import wiz  # noqa: E402  registers the type

try:
    __version__ = version("little-sister-wiz")
except PackageNotFoundError:  # running from a source tree with no install
    __version__ = "0+unknown"

__all__ = ["wiz"]
