#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.12"
# dependencies = [
# ]
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

"""Exit with success if every testing package is locked to its main package's version.

Checks that the two packages report the same version, and that each pins the other to
exactly that version in its pyproject.toml -- the main package in its ``testing`` extra,
the testing package in its dependencies.

Otherwise exit with failure and output every problem found to stdout.
"""

import json
import pathlib
import re
import subprocess
import sys

import tomllib

_REPO_ROOT = pathlib.Path(__file__).parent.parent
_PIN = re.compile(r'^\s*(?P<name>[A-Za-z0-9._-]+)\s*(?:\[[^\]]*\])?\s*==\s*(?P<version>[^\s,;]+)')


def _normalize(name: str) -> str:
    """Return the PEP 503 normalized form of a distribution name."""
    return re.sub(r'[-_.]+', '-', name).lower()


def _pyproject(path: str) -> dict[str, object]:
    with (_REPO_ROOT / path / 'pyproject.toml').open('rb') as f:
        return tomllib.load(f)


def _pinned_version(requirements: list[str], name: str) -> str | None:
    """Return the version ``name`` is pinned to with ``==``, or None if it isn't pinned."""
    for requirement in requirements:
        match = _PIN.match(requirement)
        if match and _normalize(match['name']) == _normalize(name):
            return match['version']
    return None


def _check_pin(
    requirements: list[str], name: str, version: str, *, described_as: str
) -> list[str]:
    """Return the problems with how ``requirements`` pins ``name`` to ``version``."""
    pinned = _pinned_version(requirements, name)
    if pinned is None:
        return [f'{described_as} does not pin {name}=={version}']
    if pinned != version:
        return [f'{described_as} pins {name}=={pinned}, expected {name}=={version}']
    return []


def _main() -> None:
    # Get package paths, names and versions.
    ls = pathlib.Path(__file__).parent / 'ls.py'
    cmd = [ls, 'packages', '--output=path', '--output=name', '--output=version']
    infos = json.loads(subprocess.check_output(cmd))
    # Split into main packages and testing packages.
    main_packages: dict[str, dict[str, str]] = {}
    testing_packages: dict[str, dict[str, str]] = {}
    for i in infos:
        if i['name'].endswith('-testing'):
            testing_packages[_normalize(i['name'])] = i
        else:
            main_packages[_normalize(i['name'])] = i
    # Output any mismatches and exit accordingly.
    problems: list[str] = []
    for name, testing in sorted(testing_packages.items()):
        main_name = name.removesuffix('-testing')
        main = main_packages[main_name]
        version = testing['version']
        # The two packages must be on the same version ...
        if main['version'] != version:
            problems.append(f'{main["name"]} ({main["version"]}) != {testing["name"]} ({version})')
            # The pins below are all expected to be that version, so don't pile on.
            continue
        # ... and each must pin the other to exactly that version, so that installing one
        # can never bring in a mismatched copy of the other.
        main_project = _pyproject(main['path']).get('project', {})
        extras = main_project.get('optional-dependencies', {})
        problems.extend(
            _check_pin(
                extras.get('testing', []),
                testing['name'],
                version,
                described_as=f'{main["path"]}/pyproject.toml [project.optional-dependencies] '
                'testing',
            )
        )
        testing_project = _pyproject(testing['path']).get('project', {})
        problems.extend(
            _check_pin(
                testing_project.get('dependencies', []),
                main['name'],
                version,
                described_as=f'{testing["path"]}/pyproject.toml [project] dependencies',
            )
        )
    for problem in problems:
        print(problem)
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    _main()
