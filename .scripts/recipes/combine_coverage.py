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

"""Combine a package's `coverage` reports."""

from __future__ import annotations

import argparse
import os
import shutil

import _common


def combine(package: str, python: str) -> None:
    """Combine the unit/functional/juju coverage data files into a single report.

    Produces a combined `.db`, an XML report, and a freshly rebuilt HTML report, then prints the
    terminal report. Any step failing aborts the process (as `set -e` did in the old recipe).
    """
    package_dir = _common.REPO_ROOT / package
    data_files: list[str] = []
    for test_id in ('unit', 'functional', 'juju'):
        data_file = f'.report/coverage-{test_id}-{python}.db'
        if (package_dir / data_file).exists():
            data_files.append(data_file)
    env = {**os.environ, 'COVERAGE_RCFILE': str(_common.COVERAGE_RCFILE)}
    prefix = _common.uv_run_prefix(package_dir, python)
    combined = f'.report/coverage-all-{python}.db'
    html_dir = f'.report/htmlcov-all-{python}'
    _common.run(
        [*prefix, 'coverage', 'combine', '--keep', f'--data-file={combined}', *data_files],
        cwd=package_dir,
        env=env,
        check=True,
    )
    _common.run(
        [
            *prefix,
            'coverage',
            'xml',
            f'--data-file={combined}',
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
            f'--data-file={combined}',
            '--show-contexts',
            f'--directory={html_dir}',
        ],
        cwd=package_dir,
        env=env,
        check=True,
    )
    _common.run(
        [*prefix, 'coverage', 'report', f'--data-file={combined}'],
        cwd=package_dir,
        env=env,
        check=True,
    )


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=None)
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    args = parser.parse_args()
    combine(args.package, _common.resolve_python(args.package, args.python))


if __name__ == '__main__':
    _main()
