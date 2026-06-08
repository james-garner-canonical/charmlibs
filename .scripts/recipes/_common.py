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

# ruff: noqa: I001  # tomllib is first-party in 3.11+

"""Shared helpers for the charmlibs `just` recipe scripts in `.scripts/recipes/`.

Stdlib-only by design. These helpers are imported by sibling PEP 723 scripts (e.g. `unit.py`),
which each declare their own third-party dependencies. Keeping this module dependency-free means
the sibling import works without any package/lockfile machinery. A shared helper needing a
third-party dependency is the signal to promote this directory to a real `uv`-managed tool.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys
import tomllib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import IO

# `.scripts/recipes/_common.py` -> repo root is three parents up.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
TEST_REQUIREMENTS = REPO_ROOT / 'test-requirements.txt'

# Lower bound of a `requires-python` specifier (see `_requires_python_minimum`).
_REQUIRES_PYTHON_LOWER_BOUND = re.compile(
    r'(?:>=|~=)'  # a `>=` or `~=` operator: the ones that set a lower bound
    r'\s*'  # optional whitespace between the operator and the version
    r'(\d+\.\d+)'  # capture just `major.minor`, stopping before any patch component
)


def parser(doc: str | None) -> argparse.ArgumentParser:
    """Return an `ArgumentParser` with the `--python` and `package` arguments the recipes share.

    `doc` becomes the parser's description (pass the recipe's `__doc__`). Recipes that take extra
    arguments can add them to the returned parser before parsing.
    """
    parser = argparse.ArgumentParser(description=doc)
    parser.add_argument('--python', default=None)
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    return parser


def resolve_python(package: str, python: str | None) -> str:
    """Return the Python version to test `package` with.

    If `python` is `None`, return the higher of 3.10 and the package's minimum Python version.
    """
    if python:
        return python
    minimum = _requires_python_minimum(REPO_ROOT / package)
    return max('3.10', minimum, key=lambda s: tuple(int(p) for p in s.split('.')))


def run(
    cmd: Sequence[str | pathlib.Path],
    *,
    cwd: pathlib.Path = REPO_ROOT,
    env: dict[str, str] | None = None,
    check: bool = True,
    stdout: IO[str] | None = None,
) -> int:
    """Echo and run a command, returning its exit code."""
    env = dict(os.environ if env is None else env)
    env.pop('VIRTUAL_ENV', None)  # Don't propagate script's ephemeral venv.
    print([str(part) for part in cmd], file=sys.stderr, flush=True)
    returncode = subprocess.call(cmd, cwd=cwd, env=env, stdout=stdout)
    if check and returncode != 0:
        sys.exit(returncode)
    return returncode


def uv_run(
    args: Sequence[str | pathlib.Path],
    *,
    pkg_dir: pathlib.Path,
    python: str,
    groups: Sequence[str] = (),
    env: dict[str, str] | None = None,
    check: bool = True,
    stdout: IO[str] | None = None,
) -> int:
    """Run `uv run ... <args>` in `pkg_dir`, returning the exit code."""
    uv = ['uv', 'run', '--with-requirements', TEST_REQUIREMENTS, '--python', python]
    if (pkg_dir / 'uv.lock').exists():
        uv.append('--locked')
    available = _dependency_groups(pkg_dir)
    for group in groups:
        if group in available:
            uv.extend(['--group', group])
    return run([*uv, *args], cwd=pkg_dir, env=env, check=check, stdout=stdout)


def _dependency_groups(pkg_dir: pathlib.Path) -> set[str]:
    """Return the PEP 735 dependency group names declared in `pyproject.toml`."""
    pyproject_toml = tomllib.loads((pkg_dir / 'pyproject.toml').read_text())
    return set(pyproject_toml.get('dependency-groups', ()))


def _requires_python_minimum(pkg_dir: pathlib.Path) -> str:
    """Return the `major.minor` lower bound of `pkg_dir`'s `requires-python`, e.g. `'3.10'`."""
    pyproject_toml = tomllib.loads((pkg_dir / 'pyproject.toml').read_text())
    requires_python = pyproject_toml.get('project', {})['requires-python']
    match = _REQUIRES_PYTHON_LOWER_BOUND.search(requires_python)
    assert match is not None
    return match.group(1)
