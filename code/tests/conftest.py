"""Pytest configuration and sys.path adjustments for local runs."""

# Ensure package imports resolve when running tests directly
import os
import sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE_DIR = os.path.join(ROOT, 'code')
# Add the repo root and the 'code' package directory to sys.path if missing
for p in (ROOT, CODE_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)
