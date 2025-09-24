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

"""Print the packages that have had a non-dev version bump to stdout as a JSON list."""

from __future__ import annotations

import argparse
import io
import json
import logging
import pathlib
import subprocess
import tarfile
import tempfile

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(str(pathlib.Path(__file__).relative_to(pathlib.Path().absolute())))
logger.setLevel(logging.DEBUG)


def _parse_args() -> tuple[str, str, bool]:
    parser = argparse.ArgumentParser()
    parser.add_argument('old_ref')
    parser.add_argument('new_ref')
    parser.add_argument('--exclude-placeholders', action='store_true')
    args = parser.parse_args()
    return args.old_ref, args.new_ref, args.exclude_placeholders


def _main(old_ref: str, new_ref: str, exclude_placeholders: bool) -> None:
    packages = _get_packages(old_ref, new_ref, exclude_placeholders=exclude_placeholders)
    print(json.dumps(packages))


def _get_packages(old_ref: str, new_ref: str, exclude_placeholders: bool) -> list[str]:
    changes = _get_changes(old_ref, new_ref)
    with tempfile.TemporaryDirectory() as td1:
        new_root = pathlib.Path(td1)
        _snapshot_repo(ref=new_ref, directory=new_root)
        all_packages = [
            str(pathlib.Path(p).relative_to(new_root))
            for p in (
                *_get_all_packages(
                    new_root, exclude='interfaces', exclude_placeholders=exclude_placeholders
                ),
                *_get_all_packages(
                    new_root / 'interfaces', exclude_placeholders=exclude_placeholders
                ),
            )
        ]
        changed_packages = sorted(changes.intersection(all_packages))
        new_versions = {p: _get_version(new_root, p) for p in changed_packages}
    with tempfile.TemporaryDirectory() as td2:
        old_root = pathlib.Path(td2)
        _snapshot_repo(ref=old_ref, directory=old_root)
        old_versions = {p: _get_version(old_root, p) for p in changed_packages}
    packages_to_release: list[str] = []
    for p in changed_packages:
        old = old_versions[p]
        new = new_versions[p]
        if new is not None and '.dev' not in new and old != new:
            packages_to_release.append(p)
            logger.info('%s: %s -> %s', p, old, new)
    return packages_to_release


def _get_changes(old_ref: str, new_ref: str) -> set[str]:
    """Return the first and first two parts of the changed paths as a set.

    e.g. If the file 'foo/bar/baz' has changed, return {'foo', 'foo/bar'}.
    """
    cmd = ['git', 'diff', '--name-only', old_ref, new_ref]
    output = subprocess.check_output(cmd, text=True)
    changes: set[str] = set()
    for line in output.strip().split('\n'):
        parts = pathlib.Path(line).parts
        changes.add(parts[0])
        changes.add(str(pathlib.Path(*parts[:2])))
    return changes


def _get_all_packages(
    root: pathlib.Path | str, exclude: str | None = None, exclude_placeholders: bool = False
) -> list[str]:
    paths: list[pathlib.Path] = []
    root = pathlib.Path(root)
    if not exclude_placeholders:
        paths.append(root / '.package')
    paths.extend(root.glob(r'[a-z]*'))
    return sorted(str(path) for path in paths if path.is_dir() and path.name != exclude)


def _snapshot_repo(ref: str, directory: pathlib.Path) -> None:
    git = subprocess.run(['git', 'archive', ref], stdout=subprocess.PIPE, check=True)
    stream = io.BytesIO(git.stdout)
    with tarfile.open(fileobj=stream) as tar:
        tar.extractall(path=directory)  # noqa: S202


def _get_version(root: pathlib.Path, package: str) -> str | None:
    if not (root / package).exists():
        return None
    logger.debug('Computing version for %s', package)
    dist_name = (
        'charmlibs'
        if package == '.package'
        else 'charmlibs-interfaces'
        if package == 'interfaces/.package'
        else 'charmlibs.' + package.replace('/', '-')
    )
    script = f'import importlib.metadata; print(importlib.metadata.version("{dist_name}"))'
    cmd = ['uv', 'run', '--no-project', '--with', f'./{package}', 'python', '-c', script]
    return subprocess.check_output(cmd, cwd=root, text=True).strip()


if __name__ == '__main__':
    _main(*_parse_args())
