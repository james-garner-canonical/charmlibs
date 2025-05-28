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

"""Output changed packages, or all packages if global config files have changed.

Assumes that the current working directory is the project root.
The git reference to diff with must be provided as a commandline argument.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import string
import subprocess

_ALPHABET = tuple(string.ascii_lowercase)
_GLOBAL_FILES = ('.github', 'justfile', 'pyproject.toml')


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('git_base_ref', default=None)
    args = parser.parse_args()
    packages = _get_changed_packages(project_root=pathlib.Path(), git_base_ref=args.git_base_ref)
    line = f'packages={json.dumps(packages)}'
    print(line)
    with pathlib.Path(os.environ['GITHUB_OUTPUT']).open('a') as f:
        print(line, file=f)


def _get_changed_packages(project_root: pathlib.Path, git_base_ref: str | None) -> list[str]:
    all_packages = sorted(
        path.name
        for path in project_root.iterdir()
        if path.is_dir() and (path.name.startswith(_ALPHABET) or path.name == '_charmlibs')
    )
    if not git_base_ref:
        print('Using all packages because no git base ref was provided.')
        return all_packages
    cmd = ['git', 'diff', '--name-only', f'origin/{git_base_ref}']
    diff = subprocess.check_output(cmd, text=True, cwd=project_root)
    changes = {path.split('/')[0] for path in diff.split('\n')}
    # record which packages have changed, or all if global config files have changed
    global_changes = [f for f in _GLOBAL_FILES if f in changes]
    if global_changes:
        print(f'Using all packages because global files were changed: {global_changes}')
        return all_packages
    changed_packages = [p for p in all_packages if p in changes]
    print(f'Using packages that are changed compared to {git_base_ref}: {changed_packages}')
    return changed_packages


if __name__ == '__main__':
    _main()
