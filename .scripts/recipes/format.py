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

"""Run `ruff check --fix` and `ruff format`, modifying files in place."""

from __future__ import annotations

import argparse
import sys

import _common


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'path', nargs='?', default='.', help='Path to format, defaults to the repo.'
    )
    args = parser.parse_args()
    sys.exit(format_path(args.path))


def format_path(path: str) -> int:
    """Run `ruff format` then `ruff check --fix`, modifying files in place."""
    ruff = ['uv', 'run', '--only-group=fast-lint', 'ruff']
    _common.run([*ruff, 'format', path])
    return _common.run([*ruff, 'check', '--fix', path])


if __name__ == '__main__':
    _main()
