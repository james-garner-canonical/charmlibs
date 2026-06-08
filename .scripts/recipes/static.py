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

"""Run `pyright` static analysis for a package."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import _common

if TYPE_CHECKING:
    from collections.abc import Sequence


def _main() -> None:
    args, pyright_args = _common.parser(__doc__).parse_known_args()
    python = _common.resolve_python(args.package, args.python)
    sys.exit(static(args.package, python, pyright_args))


def static(package: str, python: str, pyright_args: Sequence[str]) -> int:
    """Run `pyright` for a package against the given Python version, returning its exit code."""
    return _common.uv_run(
        [
            *('--with', 'pytest-interface-tester'),
            *('pyright', f'--pythonversion={python}', *pyright_args),
        ],
        pkg_dir=_common.REPO_ROOT / package,
        python=python,
        groups=['lint', 'unit', 'functional', 'integration'],
        check=False,
    )


if __name__ == '__main__':
    _main()
