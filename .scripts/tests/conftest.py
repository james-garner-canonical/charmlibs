# Copyright 2025 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pytest configuration for the .scripts tests.

The CLI scripts in .scripts/ use hyphenated filenames, so they can't be imported
with a normal import statement. Load each one via importlib and register it in
sys.modules under an importable (underscored) name, so test modules can simply
``import <name>``.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent


def _load(filename: str) -> None:
    """Import a hyphenated script under an underscored name in sys.modules."""
    name = pathlib.Path(filename).stem.replace('-', '_')
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / filename)
    if spec is None or spec.loader is None:
        raise ImportError(f'Could not load script: {filename}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


_load('import-discourse-docs.py')
