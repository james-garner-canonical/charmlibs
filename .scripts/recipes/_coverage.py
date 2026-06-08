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

"""Run a package's test suite under coverage, and combine the resulting reports.

`run_coverage` is imported by `unit.py`, and `combine` by `combine_coverage.py`. This module is
also runnable directly (`_coverage.py <package> <suite> [pytest args...]`): the `functional` recipe
invokes it that way via `_functional.sh`, so the coverage run happens inside the shell that has
sourced the package's `setup.sh`/`teardown.sh`. See `README.md`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from typing import TYPE_CHECKING

import _common

if TYPE_CHECKING:
    from collections.abc import Sequence

COVERAGE_RCFILE = _common.REPO_ROOT / 'pyproject.toml'


def _env() -> dict[str, str]:
    """Return the child environment for `coverage`, pointing it at the repo's config file."""
    return {**os.environ, 'COVERAGE_RCFILE': str(COVERAGE_RCFILE)}


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
    env = _env()

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


def combine(package: str, python: str) -> None:
    """Combine the unit/functional/juju coverage data files into a single report.

    Produces a combined `.db`, an XML report, and a freshly rebuilt HTML report, then prints the
    terminal report. Any step failing aborts the process (as `set -e` did in the old recipe).
    """
    package_dir = _common.REPO_ROOT / package
    data_files: list[str] = [
        f
        for test_id in ('unit', 'functional', 'juju')
        if (package_dir / (f := f'.report/coverage-{test_id}-{python}.db')).exists()
    ]
    env = _env()

    def _uv(cmd: list[str]) -> int:
        return _common.uv_run(cmd, package_dir=package_dir, python=python, env=env, check=True)

    # Combine reports and generate XML.
    data_file = f'--data-file=.report/coverage-all-{python}.db'
    _uv(['coverage', 'combine', '--keep', data_file, *data_files])
    _uv(['coverage', 'xml', data_file, '-o', f'.report/coverage-all-{python}.xml'])
    # Rebuild the HTML report from scratch (let coverage recreate the directory).
    html_dir = f'.report/htmlcov-all-{python}'
    shutil.rmtree(package_dir / html_dir, ignore_errors=True)
    _uv(['coverage', 'html', data_file, '--show-contexts', f'--directory={html_dir}'])
    # Print the report last.
    _uv(['coverage', 'report', data_file])


if __name__ == '__main__':
    _main()
