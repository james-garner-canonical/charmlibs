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

"""Parse functional test suites for requirements.

Assumes that the current working directory is the project root.
The package name must be provided as a positional commandline argument.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib


def _parse_args() -> pathlib.Path:
    parser = argparse.ArgumentParser()
    parser.add_argument('package', type=pathlib.Path)
    args = parser.parse_args()
    return args.package


def _main(package: pathlib.Path) -> None:
    requirements = _get_requirements(package)
    lines = '\n'.join(f'{k}={json.dumps(v)}' for k, v in requirements.items())
    print(lines)
    with pathlib.Path(os.environ['GITHUB_OUTPUT']).open('a') as f:
        print(lines, file=f)


def _get_requirements(package: pathlib.Path) -> dict[str, list[str]]:
    functional_dir = package / 'tests' / 'functional'
    requirements: dict[str, list[str]] = {
        'os': ['ubuntu-latest'],
        'pebble': ['no-pebble'],
        'requires': [],
    }
    if (path := functional_dir / '.os').exists():
        requirements['os'] = json.loads(path.read_text().strip())
    if (path := functional_dir / '.pebble').exists():
        requirements['pebble'] = json.loads(path.read_text().strip())
        requirements['requires'].append('pebble')
    if (path := functional_dir / '.sudo').exists():
        requirements['requires'].append('sudo')
    return requirements


if __name__ == '__main__':
    _main(package=_parse_args())
