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

"""Run linting (`ruff`) and static analysis (`pyright`) for a package."""

from __future__ import annotations

import argparse
import sys

import _common
import fast_lint
import static


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=None)
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    args, pyright_args = parser.parse_known_args()
    python = _common.resolve_python(args.package, args.python)
    failures = fast_lint.fast_lint(args.package)
    if static.static(args.package, python, pyright_args) != 0:
        failures += 1
    sys.exit(failures)


if __name__ == '__main__':
    _main()
