"""Pytest configuration and sys.path adjustments for local runs."""

# Ensure package imports resolve when running tests directly
import os
import sys
import pytest

# Get the repository root (two levels up from this file)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE_DIR = os.path.join(ROOT, 'code')

# Add the repo root and the 'code' package directory to sys.path if missing
for p in (ROOT, CODE_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture(autouse=True)
def ensure_test_environment():
    """Automatically ensure test environment is set up correctly for all tests."""
    # Save original environment
    original_env = os.environ.copy()
    
    # Set up test-friendly environment variables
    os.environ['ALLOW_MUST_HAVES'] = '1'  # Enable feature for tests
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)
