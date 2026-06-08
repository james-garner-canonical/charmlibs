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

"""Run the unit tests for the repository tooling in `.scripts/`."""

from __future__ import annotations

import sys

import _common

_TESTS = ('.scripts/tests', '.scripts/recipes/tests')


def _main() -> None:
    _common.run([
        *('uv', 'run', '--with-requirements', _common.TEST_REQUIREMENTS, '--python', '3.12'),
        *('pytest', '--tb=native', '-vv', *_TESTS, *(sys.argv[1:] or ['-rA'])),
    ])


if __name__ == '__main__':
    _main()
