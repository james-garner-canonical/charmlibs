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

"""Run `pyright` static analysis for a package."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

import _common

if TYPE_CHECKING:
    from collections.abc import Sequence


def static(package: str, python: str, pyright_args: Sequence[str]) -> int:
    """Run `pyright` for a package against the given Python version, returning its exit code.

    Mirrors the old `static` recipe: run with every dependency group installed, plus
    `pytest-interface-tester`, so that pyright can resolve all of the package's test imports.
    """
    package_dir = _common.REPO_ROOT / package
    prefix = _common.uv_run_prefix(
        package_dir, python, groups=['lint', 'unit', 'functional', 'integration']
    )
    command = [
        *prefix,
        '--with',
        'pytest-interface-tester',
        'pyright',
        f'--pythonversion={python}',
        *pyright_args,
    ]
    return _common.run(command, cwd=package_dir)


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=None)
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    args, pyright_args = parser.parse_known_args()
    python = _common.resolve_python(args.package, args.python)
    sys.exit(static(args.package, python, pyright_args))


if __name__ == '__main__':
    _main()
