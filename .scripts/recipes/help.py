#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

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

"""Describe usage and list the available recipes."""

from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING

import _common

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator

# A public recipe header in the justfile, e.g. `pack-k8s *args:`. Private `_...` recipes are
# excluded (the leading `[a-z]` doesn't match `_`), as are `set`/`mod` lines (no trailing colon).
_RECIPE = re.compile(r'^([a-z][\w-]*)[^:\n]*:[ \t]*$', re.MULTILINE)


def _main() -> None:
    print('All recipes require `uv` to be available.\n')
    print('Available recipes:')
    recipes = list(_recipes())
    width = max(len(name) for name, _ in recipes)
    for name, summary in recipes:
        print(f'    {name:<{width}}  {summary}')


def _recipes() -> Iterator[tuple[str, str]]:
    """Yield (recipe, summary) for each public recipe, in justfile order.

    The recipe names and their order come from the justfile (the single source of truth). Each
    name maps to its backing script by replacing hyphens with underscores (e.g. `pack-k8s` ->
    `pack_k8s.py`), and the summary is the first line of that script's module docstring.
    """
    recipes_dir = _common.REPO_ROOT / '.scripts' / 'recipes'
    justfile = (_common.REPO_ROOT / 'justfile').read_text()
    for name in _RECIPE.findall(justfile):
        yield name, _summary(recipes_dir / f'{name.replace("-", "_")}.py')


def _summary(path: pathlib.Path) -> str:
    """Return the first line of a script's module docstring (read without importing it)."""
    docstring = ast.get_docstring(ast.parse(path.read_text())) or ''
    return docstring.splitlines()[0] if docstring else ''


if __name__ == '__main__':
    _main()
