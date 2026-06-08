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

"""`lint`, `unit` test, and build the `docs` for a package."""

from __future__ import annotations

import argparse
import sys

import _common


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=None)
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    args = parser.parse_args()
    recipes = _common.REPO_ROOT / '.scripts' / 'recipes'
    python_flag = ['--python', args.python] if args.python is not None else []
    steps = [
        [str(recipes / 'lint.py'), args.package, *python_flag],
        [str(recipes / 'unit.py'), args.package, *python_flag],
        # docs.just isn't migrated yet, so delegate the docs build to the `docs` just module.
        ['just', 'docs', 'html', args.package],
    ]
    returncode = 0
    for command in steps:
        returncode = _common.run(command, cwd=_common.REPO_ROOT)
        if returncode != 0:
            break  # fail fast, like the old dependency recipe
    sys.exit(returncode)


if __name__ == '__main__':
    _main()
