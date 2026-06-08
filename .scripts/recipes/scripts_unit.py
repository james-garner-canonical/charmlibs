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

"""Run the unit tests for the repository tooling in `.scripts/`."""

from __future__ import annotations

import argparse
import sys

import _common

# Test directories for the repository tooling scripts.
_TEST_DIRS = ['.scripts/tests', '.scripts/recipes/tests']


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=None)
    args, pytest_args = parser.parse_known_args()
    # These tests aren't tied to a package: run from the repo root, without `--locked` or any
    # dependency groups, so this builds the `uv run` command directly rather than via
    # `_common.uv_run` (which is shaped for the per-package recipes).
    python = args.python or _common.DEFAULT_PYTHON
    cmd = [
        *('uv', 'run', '--with-requirements', str(_common.TEST_REQUIREMENTS), '--python', python),
        *('pytest', '--tb=native', '-vv', *(pytest_args or ['-rA'])),
        *_TEST_DIRS,
    ]
    sys.exit(_common.run(cmd))


if __name__ == '__main__':
    _main()
