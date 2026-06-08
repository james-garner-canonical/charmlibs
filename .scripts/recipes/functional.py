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

"""Run functional tests with `coverage` for a package.

Functional tests often need a package-provided `tests/functional/setup.sh` and `teardown.sh`,
which must be *sourced* by a single long-lived shell: they export environment variables, set the
umask, and start/stop background processes (e.g. pebble) whose lifetime spans the whole test run.

That sourcing is the one piece of irreducible bash, kept in `_functional.sh`. We run it with the
working directory set to the package, passing `_coverage.py` as the command to run between setup
and teardown.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import _common


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=None)
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    args, pytest_args = parser.parse_known_args()
    python = _common.resolve_python(args.package, args.python)
    package_dir = _common.REPO_ROOT / args.package
    source_wrapper = pathlib.Path(__file__).with_name('_functional.sh')
    coverage_script = pathlib.Path(__file__).with_name('_coverage.py')
    cmd = [
        str(source_wrapper),
        str(coverage_script),
        args.package,
        'functional',
        '--python',
        python,
        *(pytest_args or ['-rA']),
    ]
    sys.exit(_common.run(cmd, cwd=package_dir))


if __name__ == '__main__':
    _main()
