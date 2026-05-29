"""Pytest configuration for Sphinx extension tests.

Adds the parent directory (.docs/) to sys.path so that modules like
``diataxis_preprocessor`` can be imported from test files.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
