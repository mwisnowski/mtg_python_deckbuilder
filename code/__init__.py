"""Root package for the MTG deckbuilder source tree.

Ensures `python -m code.*` resolves to this project and adjusts sys.path so
legacy absolute imports like `import logging_util` (modules living under this
package) work whether you run files directly or as modules.
"""

from __future__ import annotations

import os
import sys

# Make the package directory importable as a top-level for legacy absolute imports
_PKG_DIR = os.path.dirname(__file__)
if _PKG_DIR and _PKG_DIR not in sys.path:
	sys.path.insert(0, _PKG_DIR)

__all__ = []
