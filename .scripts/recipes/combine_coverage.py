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
    data_files: list[str] = [
        f
        for test_id in ('unit', 'functional', 'juju')
        if (package_dir / (f := f'.report/coverage-{test_id}-{python}.db')).exists()
    ]
    env = {**os.environ, 'COVERAGE_RCFILE': str(_common.COVERAGE_RCFILE)}

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
