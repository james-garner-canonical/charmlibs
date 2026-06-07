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

"""Pytest configuration for the .scripts/recipes tests.

Add the recipes directory to sys.path so the recipe scripts and their shared modules can be
imported (they rely on sibling imports, exactly as they do when run via `uv run --script`).
"""

import pathlib
import sys

_RECIPES_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_RECIPES_DIR))
