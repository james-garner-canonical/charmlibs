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

"""Shared helpers for the charmlibs `just` recipe scripts in `.scripts/recipes/`.

Stdlib-only by design. These helpers are imported by sibling PEP 723 scripts (e.g. `unit.py`),
which each declare their own third-party dependencies. Keeping this module dependency-free means
the sibling import works without any package/lockfile machinery. A shared helper needing a
third-party dependency is the signal to promote this directory to a real `uv`-managed tool.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import IO

# `.scripts/recipes/_common.py` -> repo root is three parents up.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
TEST_REQUIREMENTS = REPO_ROOT / 'test-requirements.txt'
COVERAGE_RCFILE = REPO_ROOT / 'pyproject.toml'
DEFAULT_PYTHON = '3.10'


def resolve_python(package: str, python: str | None) -> str:
    """Return the Python version to test `package` with.

    For now this is the explicitly requested `python`, falling back to `DEFAULT_PYTHON`. The
    `package` is accepted (and will be used) for a planned change: defaulting to the package's own
    minimum supported version, read from its `pyproject.toml` `requires-python`.
    """
    return python or DEFAULT_PYTHON


def uv_run_prefix(
    package_dir: pathlib.Path, python: str, *, groups: Sequence[str] = ()
) -> list[str]:
    """Build the `uv run` command prefix shared by the package test recipes.

    Run with the repo-level `test-requirements.txt` constraints and the requested Python, adding
    `--locked` when the package has a `uv.lock`, plus any requested dependency groups.
    """
    cmd = ['uv', 'run', '--with-requirements', str(TEST_REQUIREMENTS), '--python', python]
    if (package_dir / 'uv.lock').exists():
        cmd.append('--locked')
    for group in groups:
        cmd += ['--group', group]
    return cmd


def run(
    cmd: Sequence[str | pathlib.Path],
    *,
    cwd: pathlib.Path,
    env: dict[str, str] | None = None,
    check: bool = False,
    stdout: IO[str] | None = None,
) -> int:
    """Echo and run a command, returning its exit code.

    The command is echoed (to stderr) as the list of its arguments, so argument boundaries are
    unambiguous. Pass `stdout` (an open text file) to redirect the command's standard output, for
    example to capture generated output in a file. When `check` is true, exit this process with the
    command's exit code on failure (mirroring the old recipes' `set -e`).

    `VIRTUAL_ENV` is dropped from the child environment. These recipes are themselves run via
    `uv run --script`, which exports `VIRTUAL_ENV` pointing at the script's ephemeral environment.
    Inheriting it would make the inner `uv` commands warn that it doesn't match the project's
    `.venv`.
    """
    env = dict(os.environ if env is None else env)
    env.pop('VIRTUAL_ENV', None)
    print([str(part) for part in cmd], file=sys.stderr, flush=True)
    returncode = subprocess.call(cmd, cwd=cwd, env=env, stdout=stdout)
    if check and returncode != 0:
        sys.exit(returncode)
    return returncode
