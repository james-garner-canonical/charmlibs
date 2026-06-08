#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.12"
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

"""Run a package's test suite under coverage, and combine the resulting reports."""

from __future__ import annotations

import argparse
import os
import shutil

import _common

COVERAGE_RCFILE = _common.REPO_ROOT / 'pyproject.toml'


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=None)
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    parser.add_argument('suite', help='Test suite name, e.g. `unit` or `functional`.')
    args, pytest_args = parser.parse_known_args()
    python = _common.resolve_python(args.package, args.python)
    run_coverage(args.package, args.suite, python=python, pytest_args=pytest_args or ['-rA'])


def run_coverage(package: str, suite: str, python: str, pytest_args: list[str]) -> None:
    """Run `coverage run -m pytest` then `coverage report` for a package's test suite."""
    pkg_dir = _common.REPO_ROOT / package
    data_file_arg = f'--data-file=.report/coverage-{suite}-{python}.db'

    def _uv(args: list[str]):
        _common.uv_run(args, pkg_dir=pkg_dir, python=python, groups=[suite], env=_env())

    _uv([
        *('coverage', 'run', data_file_arg, '--source=src', '-m'),
        *('pytest', '--tb=native', '-vv', f'tests/{suite}', *pytest_args),
    ])
    _uv(['coverage', 'report', data_file_arg])


def combine(package: str, python: str) -> None:
    """Combine the unit/functional/juju coverage data files into a single report."""
    pkg_dir = _common.REPO_ROOT / package
    data_files: list[str] = [
        f
        for test_id in ('unit', 'functional', 'juju')
        if (pkg_dir / (f := f'.report/coverage-{test_id}-{python}.db')).exists()
    ]

    def _uv(cmd: list[str]):
        _common.uv_run(cmd, pkg_dir=pkg_dir, python=python, env=_env())

    # Combine reports and generate XML.
    data_file_arg = f'--data-file=.report/coverage-all-{python}.db'
    _uv(['coverage', 'combine', '--keep', data_file_arg, *data_files])
    _uv(['coverage', 'xml', data_file_arg, '-o', f'.report/coverage-all-{python}.xml'])
    # Rebuild the HTML report from scratch (let coverage recreate the directory).
    html_dir = f'.report/htmlcov-all-{python}'
    shutil.rmtree(pkg_dir / html_dir, ignore_errors=True)
    _uv(['coverage', 'html', data_file_arg, '--show-contexts', f'--directory={html_dir}'])
    # Print the report last.
    _uv(['coverage', 'report', data_file_arg])


def _env() -> dict[str, str]:
    return {**os.environ, 'COVERAGE_RCFILE': str(COVERAGE_RCFILE)}


if __name__ == '__main__':
    _main()
