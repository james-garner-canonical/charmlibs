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

"""Run `ruff`, failing afterwards if any errors are found."""

from __future__ import annotations

import argparse
import sys

import _common


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', nargs='?', default='.', help='Path to lint, defaults to the repo.')
    args = parser.parse_args()
    sys.exit(fast_lint(args.path))


def fast_lint(path: str) -> int:
    """Run `ruff check` and `ruff format --diff`, returning the number of failing commands.

    The `ruff check --diff` output (the fixes that would resolve `ruff check` issues) is printed
    for information, but never counts as a failure. Mirrors the old `fast-lint` recipe.
    """
    ruff = ['uv', 'run', '--only-group=fast-lint', 'ruff']
    failures = 0
    if _common.run([*ruff, 'check', path], check=False) != 0:
        failures += 1
    _common.run([*ruff, 'check', '--diff', path], check=False)
    if _common.run([*ruff, 'format', '--diff', path], check=False) != 0:
        failures += 1
    return failures


if __name__ == '__main__':
    _main()
