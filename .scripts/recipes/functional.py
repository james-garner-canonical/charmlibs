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

"""Run functional tests with coverage, sourcing the package's setup/teardown scripts.

Functional tests often need a package-provided `tests/functional/setup.sh` and `teardown.sh`,
which must be *sourced* by a single long-lived shell: they export environment variables, set the
umask, and start/stop background processes (e.g. pebble) whose lifetime spans the whole test run.

That sourcing is the one piece of irreducible bash. We run a small, static wrapper script (no
interpolation -- arguments are passed positionally) that sources setup, runs `_coverage.py` in that
same shell, sources teardown, and propagates the exit code.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

import _common

# Static wrapper: `$1` is the package dir, `$2...` is the command to run in the sourced shell.
# Nothing is interpolated, so there's no quoting/injection surface: values arrive as separate argv.
_SOURCE_SETUP_TEARDOWN = r"""
set -ueo pipefail
cd "$1"
shift
if [ -e tests/functional/setup.sh ]; then
    source ./tests/functional/setup.sh
fi
set +e
"$@"
returncode=$?
set -e
if [ -e tests/functional/teardown.sh ]; then
    source ./tests/functional/teardown.sh
fi
exit "$returncode"
"""


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default='3.10')
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    args, pytest_args = parser.parse_known_args()
    package_dir = _common.REPO_ROOT / args.package
    coverage_script = pathlib.Path(__file__).with_name('_coverage.py')
    inner = [
        str(coverage_script),
        args.package,
        'functional',
        '--python',
        args.python,
        *(pytest_args or ['-rA']),
    ]
    cmd = ['bash', '-c', _SOURCE_SETUP_TEARDOWN, 'bash', str(package_dir), *inner]
    print('+', ' '.join(inner), file=sys.stderr, flush=True)
    sys.exit(subprocess.call(cmd))


if __name__ == '__main__':
    _main()
