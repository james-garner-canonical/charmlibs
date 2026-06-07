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
the sibling import works without any package/lockfile machinery. See `thin-justfile-notes.md`.
"""

from __future__ import annotations

import pathlib
import shlex
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# `.scripts/recipes/_common.py` -> repo root is three parents up.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
TEST_REQUIREMENTS = REPO_ROOT / 'test-requirements.txt'
COVERAGE_RCFILE = REPO_ROOT / 'pyproject.toml'


def uv_run_prefix(
    package_dir: pathlib.Path, python: str, *, groups: Sequence[str] = ()
) -> list[str]:
    """Build the `uv run` command prefix shared by the test recipes.

    Mirrors the `_uv_run_with_test_requirements` justfile variable: run with the repo-level
    `test-requirements.txt` constraints and the requested Python, adding `--locked` when the
    package has a `uv.lock`, plus any requested dependency groups.
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
) -> int:
    """Echo and run a command, returning its exit code.

    The echoed line is `shlex.quote`d so it can be copy-pasted, matching the visibility that
    `set -x` gave the old bash recipes. When `check` is true, exit this process with the
    command's exit code on failure (mirroring `set -e`).
    """
    print('+', shlex.join(str(part) for part in cmd), file=sys.stderr, flush=True)
    returncode = subprocess.call(cmd, cwd=cwd, env=env)
    if check and returncode != 0:
        sys.exit(returncode)
    return returncode
