#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.10"
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
import subprocess
from typing import TYPE_CHECKING

import _common

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator

# A public recipe header in the justfile, e.g. `pack-k8s *args:`. Private `_...` recipes are
# excluded (the leading `[a-z]` doesn't match `_`), as are `set`/`mod` lines (no trailing colon).
_RECIPE = re.compile(r'^([a-z][\w-]*)[^:\n]*:\s*$')
# The script a recipe forwards to, e.g. `@.scripts/recipes/pack.py --substrate=k8s "$@"`.
_SCRIPT = re.compile(r'\.scripts/recipes/(\w+)\.py')
# The substrate a shared-script recipe selects, used to tell e.g. `pack-k8s` from `pack-machine`.
_SUBSTRATE = re.compile(r'--substrate=(\w+)')
# Submodules loaded by the justfile, listed (with their own `[doc]`) after the top-level recipes.
_SUBMODULES = ['interface', 'docs']


def _recipes() -> Iterator[tuple[str, str]]:
    """Yield (recipe, summary) for each public recipe, in justfile order.

    The recipe names and their order come from the justfile (the single source of truth). Each
    summary is the first line of the backing script's module docstring, with the `--substrate`
    appended where one recipe name maps to a shared script (e.g. `pack-k8s` and `pack-machine`).
    """
    recipes_dir = _common.REPO_ROOT / '.scripts' / 'recipes'
    lines = (_common.REPO_ROOT / 'justfile').read_text().splitlines()
    for index, line in enumerate(lines):
        match = _RECIPE.match(line)
        if match is None:
            continue
        name = match.group(1)
        # The script is referenced in the recipe body, on one of the following indented lines.
        for body in lines[index + 1 :]:
            if body and not body[0].isspace():
                break  # reached the next top-level item without finding a script
            script = _SCRIPT.search(body)
            if script is None:
                continue
            summary = _summary(recipes_dir / f'{script.group(1)}.py')
            substrate = _SUBSTRATE.search(body)
            if substrate is not None:
                summary = f'{summary} [{substrate.group(1)}]'
            yield name, summary
            break


def _summary(path: pathlib.Path) -> str:
    """Return the first line of a script's module docstring (read without importing it)."""
    docstring = ast.get_docstring(ast.parse(path.read_text())) or ''
    return docstring.splitlines()[0] if docstring else ''


def _submodule_recipes(module: str) -> list[str]:
    """Return `just`'s recipe listing for a submodule, which keeps its own `[doc]` descriptions."""
    listing = subprocess.run(
        ['just', '--list', module, '--unsorted'],
        cwd=_common.REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()
    return [line for line in listing if line.strip() and line.strip() != 'Available recipes:']


def _main() -> None:
    print('All recipes require `uv` to be available.\n')
    print('Available recipes:')
    recipes = list(_recipes())
    width = max(len(name) for name, _ in recipes)
    for name, summary in recipes:
        print(f'    {name:<{width}}  {summary}')
    for module in _SUBMODULES:
        print(f'\n{module}:')
        for line in _submodule_recipes(module):
            print(f'    {line}')


if __name__ == '__main__':
    _main()
