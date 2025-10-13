#!/usr/bin/env -S uv run --script --no-project

# Copyright 2024 Canonical Ltd.
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

"""Output changed packages, or all packages if global config files have changed."""

from __future__ import annotations

import argparse
import logging
import os
import pathlib
import subprocess

_GLOBAL_FILES = {'.github', '.scripts', 'justfile', 'pyproject.toml'}
_REPO_ROOT = pathlib.Path(__file__).parent.parent

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(str(pathlib.Path(__file__).relative_to(_REPO_ROOT)))


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('category', choices=('packages', 'interfaces'))
    parser.add_argument('git_base_ref', nargs='?', default='')
    parser.add_argument('--name-only', action='store_true')
    args = parser.parse_args()
    cmd = ['.scripts/ls.py', args.category]
    if not args.git_base_ref:
        logger.info('Using all packages because no git base ref was provided:')
    elif global_changes := _get_global_changes(args.git_base_ref):
        logger.info('Using all packages because global files were changed: %s', global_changes)
    else:
        cmd.append(args.git_base_ref)
    if args.name_only:
        cmd.append('--name-only')
    result = subprocess.check_output(cmd, text=True).strip()
    output = f'result={result}'
    logger.info(output)
    with pathlib.Path(os.environ['GITHUB_OUTPUT']).open('a') as f:
        print(output, file=f)


def _get_global_changes(git_base_ref: str) -> list[str]:
    cmd = ['git', 'diff', '--name-only', git_base_ref]
    diff = subprocess.check_output(cmd, text=True).strip().splitlines()
    changes = {c.split('/')[0] for c in diff}
    return sorted(_GLOBAL_FILES.intersection(changes))


if __name__ == '__main__':
    _main()
