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

"""`lint`, `unit` test, and build the `docs` for a package."""

from __future__ import annotations

import _common


def _main() -> None:
    args = _common.parser(__doc__).parse_args()
    python = _common.resolve_python(args.package, args.python)
    for cmd in [
        [_common.REPO_ROOT / '.scripts' / 'recipes' / 'lint.py', args.package, '--python', python],
        [_common.REPO_ROOT / '.scripts' / 'recipes' / 'unit.py', args.package, '--python', python],
        ['just', 'docs', 'html', args.package],
    ]:
        _common.run(cmd)


if __name__ == '__main__':
    _main()
