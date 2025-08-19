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

"""Output the packages to publish, PyPI repository-url and whether to skip Juju tests when publishing."""

from __future__ import annotations

import io
import json
import logging
import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile

logging.basicConfig(level=logging.DEBUG)


def _main() -> None:
    event_name = os.environ['GITHUB_EVENT_NAME']
    event = json.loads(pathlib.Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    if event_name == 'push':
        _output({
            'packages': json.dumps(_get_bumped_packages(event['before'], os.environ['GITHUB_SHA'])),
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


def _get_bumped_packages(ref_before: str, ref_after: str) -> list[str]:
    changes = _get_changes(ref_before, ref_after)
    with tempfile.TemporaryDirectory() as tempdirname:
        tempdir = pathlib.Path(tempdirname)
        root_before = _git_archive(ref=ref_before, path=tempdir / '.before')
        root_after = _git_archive(ref=ref_after, path=tempdir / '.after')
        all_packages_raw = (
            *_get_all_packages(root_after, exclude='interfaces'),
            *_get_all_packages(root_after / 'interfaces'),
        )
        all_packages = [str(pathlib.Path(p).relative_to(root_after)) for p in all_packages_raw]
        changed_packages = sorted(changes.intersection(all_packages))
        versions_after = {p: _get_version(root_after, p) for p in changed_packages}
        versions_before = {p: _get_version(root_before, p) for p in changed_packages}
    changed = [p for p in changed_packages if versions_before[p] != versions_after[p]]
    for p in changed:
        logging.info('%s: %s -> %s', p, versions_before[p], versions_after[p])
    return changed


def _get_changes(before: str, after: str) -> set[str]:
    cmd = ['git', 'diff', '--name-only', before, after]
    output = subprocess.check_output(cmd, text=True)
    diff = [p.split('/') for p in output.split('\n')]
    return {*(p[0] for p in diff), *('/'.join(p[:2]) for p in diff)}


def _get_all_packages(root: pathlib.Path | str, exclude: str | None = None) -> list[str]:
    root = pathlib.Path(root)
    paths = [root / '.package', *root.glob(r'[a-z]*')]
    return sorted(str(path) for path in paths if path.is_dir() and path.name != exclude)


def _git_archive(ref: str, path: pathlib.Path) -> pathlib.Path:
    path.mkdir()
    git = subprocess.run(['git', 'archive', ref], stdout=subprocess.PIPE, check=True)
    stream = io.BytesIO(git.stdout)
    with tarfile.open(fileobj=stream) as tar:
        tar.extractall(path=path)  # noqa: S202
    return path


def _get_version(root: pathlib.Path, package: str) -> str | None:
    if not (root / package).exists():
        return None
    logging.debug('Computing version for %s', package)
    dist_name = (
        'charmlibs' if package == '.package'
        else 'charmlibs-interfaces' if package == 'interfaces/.package'
        else 'charmlibs.' + package.replace('/', '-')
    )
    script = f'import importlib.metadata; print(importlib.metadata.version("{dist_name}"))'
    cmd = ['uv', 'run', '--no-project', '--with', f'./{package}', 'python', '-c', script]
    return subprocess.check_output(cmd, cwd=root, text=True).strip()


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
