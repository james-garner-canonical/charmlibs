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

"""Run `uv add` for a package, respecting repo-level version constraints.

Example: `add.py pathops 'pydantic>=2'` adds a constrained dependency to pathops.
"""

from __future__ import annotations

import argparse
import sys

import _common


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    args, uv_add_args = parser.parse_known_args()
    package_dir = _common.REPO_ROOT / args.package
    command = ['uv', 'add', '--constraints', str(_common.TEST_REQUIREMENTS), *uv_add_args]
    sys.exit(_common.run(command, cwd=package_dir))


if __name__ == '__main__':
    _main()
