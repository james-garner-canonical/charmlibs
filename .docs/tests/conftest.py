"""Pytest configuration for docs tests.

Adds ``extensions/`` and ``scripts/`` to sys.path so that Sphinx
extensions and the diataxis preprocessor can be imported from test files.
"""

import pathlib
import sys

_DOCS_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_DOCS_DIR / 'extensions'))
sys.path.insert(0, str(_DOCS_DIR / 'scripts'))
