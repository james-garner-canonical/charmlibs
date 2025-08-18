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

# /// script
# requires-python = '>=3.8'
# dependencies = [
#     'tomli',
# ]
# ///

"""Output the packages to publish, PyPI repository-url and whether to skip Juju tests when publishing."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import typing

import tomli


def _main() -> None:
    event_name = os.environ['GITHUB_EVENT_NAME']
    event = json.loads(pathlib.Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    if event_name == 'push':
        _output({
            'packages': json.dumps(_packages(event['before'], os.environ['GITHUB_SHA'])),
            'skip-juju': 'false',
            'repository-url': 'https://upload.pypi.org/legacy/',
        })
    elif event_name == 'workflow_dispatch':
        _output({
            'packages': json.dumps([event['inputs']['package']]),
            'skip-juju': event['inputs']['skip-juju'],
            'repository-url': 'https://test.pypi.org/legacy/',
        })
    else:
        print(f'Unexpected event name: {event_name}')
        sys.exit(1)


def _packages(before: str, after: str) -> list[str]:
    packages = _get_changed_packages(before, after)
    _git_checkout(before)
    versions_before = {p: _get_version(p) for p in packages}
    _git_checkout(after)
    versions_after = {p: _get_version(p) for p in packages}
    return [p for p in packages if versions_before[p] != versions_after[p]]


def _get_changed_packages(before: str, after: str) -> list[str]:
    all_packages = [*_get_packages('.', exclude='interfaces'), *_get_packages('interfaces')]
    cmd = ['git', 'diff', '--name-only', before, after]
    output = subprocess.check_output(cmd, text=True)
    diff = [p.split('/') for p in output.split('\n')]
    changes = {*(p[0] for p in diff), *('/'.join(p[:2]) for p in diff)}
    return sorted(changes.intersection(all_packages))


def _get_packages(root: pathlib.Path | str, exclude: str | None = None) -> list[str]:
    root = pathlib.Path(root)
    paths = [root / '.package', *root.glob(r'[a-z]*')]
    return sorted(str(path) for path in paths if path.is_dir() and path.name != exclude)


def _git_checkout(ref: str) -> None:
    cmd = ['git', 'checkout', ref]
    subprocess.check_output(cmd)


def _get_version(package: str) -> str | None:
    pyproject = pathlib.Path(package) / 'pyproject.toml'
    if not pyproject.exists():
        return None
    text = pyproject.read_text()
    toml = tomli.loads(text)
    proj = toml['project']
    if (version := proj.get('version')) is not None:
        return version
    assert 'dynamic' in proj
    assert 'version' in proj['dynamic']
    build = toml['build-system']
    backend = build['build-backend']
    if 'hatch' in backend:
        return _get_version_from_hatch(package, toml)
    if 'setuptools' in backend:
        return _get_version_from_setuptools(package, toml)
    raise NotImplementedError(f'Unsupported build backend: {backend!r}')


def _get_version_from_hatch(package: str, toml: dict[str, typing.Any]) -> str:
    output = subprocess.check_output(['uvx', 'hatch', 'version'], cwd=package, text=True)
    assert output
    return output.strip()


def _get_version_from_setuptools(package: str, toml: dict[str, typing.Any]) -> str:
    dynamic = toml['tools']['setuptools']['dynamic']['version']
    if (path := dynamic.get('file')) is not None:
        return (pathlib.Path(package) / path).read_text()
    if (path := dynamic.get('attr')) is not None:
        raise NotImplementedError('Support for `attr` is not yet implemented.')
    raise ValueError(f'Unknown dynamic version specification: {dynamic}')


def _output(di: dict[str, str]) -> None:
    for v in di.values():
        if not isinstance(v, str):  # type: ignore
            print(f'Unexpected type {type(v)} for value: v')
            sys.exit(1)
    output = '\n'.join(f'{k}={v}' for k, v in di.items())
    with pathlib.Path(os.environ['GITHUB_OUTPUT']).open('a') as f:
        print(output)
        print(output, file=f)


if __name__ == '__main__':
    _main()
