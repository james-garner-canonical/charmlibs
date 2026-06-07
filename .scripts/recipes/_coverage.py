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

"""Coverage logic shared by the `unit`, `functional`, and `combine-coverage` recipes.

`run_coverage` and `combine` are imported by the sibling recipe scripts. This module is also
runnable directly (`_coverage.py <package> <suite> [pytest args...]`): the `functional` recipe
invokes it that way so the coverage run happens inside the shell that has sourced the package's
`setup.sh`/`teardown.sh` (see `functional.py`).
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


def run_coverage(package: str, suite: str, python: str, pytest_args: Sequence[str]) -> int:
    """Run `coverage run -m pytest` then `coverage report` for a package's test suite.

    Returns the exit code. As in the previous bash recipe, the report step is skipped if the
    test run fails, and that failing exit code is returned.
    """
    package_dir = _common.REPO_ROOT / package
    data_file = f'.report/coverage-{suite}-{python}.db'
    env = {**os.environ, 'COVERAGE_RCFILE': str(_common.COVERAGE_RCFILE)}
    prefix = _common.uv_run_prefix(package_dir, python, groups=[suite])
    returncode = _common.run(
        [
            *prefix,
            'coverage',
            'run',
            f'--data-file={data_file}',
            '--source=src',
            '-m',
            'pytest',
            '--tb=native',
            '-vv',
            *pytest_args,
            f'tests/{suite}',
        ],
        cwd=package_dir,
        env=env,
    )
    if returncode != 0:
        return returncode
    return _common.run(
        [*prefix, 'coverage', 'report', f'--data-file={data_file}'],
        cwd=package_dir,
        env=env,
    )


def combine(package: str, python: str) -> None:
    """Combine the unit/functional/juju coverage data files into a single report.

    Produces a combined `.db`, an XML report, and a freshly rebuilt HTML report, then prints the
    terminal report. Any step failing aborts the process (as `set -e` did before).
    """
    package_dir = _common.REPO_ROOT / package
    data_files = [
        f
        for f in (
            f'.report/coverage-{test_id}-{python}.db' for test_id in ('unit', 'functional', 'juju')
        )
        if (package_dir / f).exists()
    ]
    env = {**os.environ, 'COVERAGE_RCFILE': str(_common.COVERAGE_RCFILE)}
    prefix = _common.uv_run_prefix(package_dir, python)
    data_file = f'.report/coverage-all-{python}.db'
    html_dir = f'.report/htmlcov-all-{python}'
    _common.run(
        [*prefix, 'coverage', 'combine', '--keep', f'--data-file={data_file}', *data_files],
        cwd=package_dir,
        env=env,
        check=True,
    )
    _common.run(
        [
            *prefix,
            'coverage',
            'xml',
            f'--data-file={data_file}',
            '-o',
            f'.report/coverage-all-{python}.xml',
        ],
        cwd=package_dir,
        env=env,
        check=True,
    )
    shutil.rmtree(
        package_dir / html_dir, ignore_errors=True
    )  # let coverage create it from scratch
    _common.run(
        [
            *prefix,
            'coverage',
            'html',
            f'--data-file={data_file}',
            '--show-contexts',
            f'--directory={html_dir}',
        ],
        cwd=package_dir,
        env=env,
        check=True,
    )
    _common.run(
        [*prefix, 'coverage', 'report', f'--data-file={data_file}'],
        cwd=package_dir,
        env=env,
        check=True,
    )


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default='3.10')
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    parser.add_argument('suite', help='Test suite name, e.g. `unit` or `functional`.')
    args, pytest_args = parser.parse_known_args()
    sys.exit(run_coverage(args.package, args.suite, args.python, pytest_args or ['-rA']))


if __name__ == '__main__':
    _main()
