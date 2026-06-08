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

"""Run a package's test suite under coverage.

`run_coverage` is imported by `unit.py`. This module is also runnable directly
(`_coverage.py <package> <suite> [pytest args...]`): the `functional` recipe invokes it that way
via `_functional.sh`, so the coverage run happens inside the shell that has sourced the package's
`setup.sh`/`teardown.sh`. See `README.md`.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import TYPE_CHECKING

import _common

if TYPE_CHECKING:
    from collections.abc import Sequence


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=None)
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    parser.add_argument('suite', help='Test suite name, e.g. `unit` or `functional`.')
    args, pytest_args = parser.parse_known_args()
    python = _common.resolve_python(args.package, args.python)
    sys.exit(run_coverage(args.package, args.suite, python, pytest_args or ['-rA']))


def run_coverage(package: str, suite: str, python: str, pytest_args: Sequence[str]) -> int:
    """Run `coverage run -m pytest` then `coverage report` for a package's test suite.

    Returns the exit code. As in the previous bash recipe, the report step is skipped if the
    test run fails, and that failing exit code is returned.
    """
    package_dir = _common.REPO_ROOT / package
    data_file = f'.report/coverage-{suite}-{python}.db'
    env = {**os.environ, 'COVERAGE_RCFILE': str(_common.COVERAGE_RCFILE)}

    def _uv(args: list[str]) -> int:
        return _common.uv_run(
            args, package_dir=package_dir, python=python, groups=[suite], env=env
        )

    run_cmd = [
        *('coverage', 'run', f'--data-file={data_file}', '--source=src'),
        *('-m', 'pytest', '--tb=native', '-vv', *pytest_args, f'tests/{suite}'),
    ]
    returncode = _uv(run_cmd)
    if returncode != 0:
        return returncode  # skip the report step if the tests failed
    return _uv(['coverage', 'report', f'--data-file={data_file}'])


if __name__ == '__main__':
    _main()
