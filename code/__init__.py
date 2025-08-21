"""Root package for the MTG deckbuilder source tree.

Adding this file ensures the directory is treated as a proper package so that
`python -m code.main` resolves to this project instead of the Python stdlib
module named `code` (which is a simple module, not a package).

If you still accidentally import the stdlib module, be sure you are executing
from the project root so the local `code` package is first on sys.path.
"""

__all__ = []
