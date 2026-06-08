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
import functools
import os
import shutil

import _common


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=None)
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    args = parser.parse_args()
    combine(args.package, _common.resolve_python(args.package, args.python))


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
    uv = functools.partial(
        _common.uv_run, package_dir=package_dir, python=python, env=env, check=True
    )
    combined = f'.report/coverage-all-{python}.db'
    xml_file = f'.report/coverage-all-{python}.xml'
    html_dir = f'.report/htmlcov-all-{python}'
    # Merge the per-suite data files into a single combined data file.
    uv(['coverage', 'combine', '--keep', f'--data-file={combined}', *data_files])
    # Write the XML report (consumed by CI and coverage services).
    uv(['coverage', 'xml', f'--data-file={combined}', '-o', xml_file])
    # Rebuild the HTML report from scratch (let coverage recreate the directory).
    shutil.rmtree(package_dir / html_dir, ignore_errors=True)
    uv([
        'coverage',
        'html',
        f'--data-file={combined}',
        '--show-contexts',
        f'--directory={html_dir}',
    ])
    # Print the terminal summary.
    uv(['coverage', 'report', f'--data-file={combined}'])


if __name__ == '__main__':
    _main()
