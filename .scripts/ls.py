#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.11"
# ///

# ruff: noqa: I001  # tomllib is first-party in 3.11+

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

"""Output the packages or interfaces in the repository as a JSON list.

See the the command-line help for options.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import io
import json
import logging
import pathlib
import re
import subprocess
import tarfile
import tempfile
import tomllib

_REPO_ROOT = pathlib.Path(__file__).parent.parent

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(str(pathlib.Path(__file__).relative_to(_REPO_ROOT)))


@dataclasses.dataclass(frozen=True)
class Info:
    """Information about a specific package or interface."""

    path: str
    name: str = ''
    version: str = ''

    def to_dict(self, *fields: str) -> dict[str, str]:
        """Return dictionary containing only specified fields."""
        return {field: getattr(self, field) for field in fields}


def _main() -> None:
    """Parse command-line arguments and output packages as JSON."""
    parser = argparse.ArgumentParser()
    parser.add_argument('category', choices=('packages', 'interfaces'))
    parser.add_argument('old_ref', nargs='?')
    parser.add_argument('new_ref', nargs='?')
    parser.add_argument('--exclude-examples', action='store_true')
    parser.add_argument('--exclude-placeholders', action='store_true')
    parser.add_argument('--only-if-version-changed', action='store_true')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--output', action='append', choices=['path', 'name', 'version'])
    group.add_argument('--name-only', action='store_true')
    args = parser.parse_args()
    single_output = 'name' if args.name_only else 'path'  # used if --output isn't specified
    infos = _ls(
        category=args.category,
        old_ref=args.old_ref,
        new_ref=args.new_ref,
        include_examples=not args.exclude_examples,
        include_placeholders=not args.exclude_placeholders,
        only_if_version_changed=args.only_if_version_changed,
        output=args.output or [single_output],
    )
    if args.output:
        result = sorted(
            (info.to_dict(*args.output) for info in infos),
            key=lambda di: tuple(di.items()),
        )
    else:
        result = sorted(getattr(info, single_output) for info in infos)
    print(json.dumps(result))


def _ls(
    category: str,
    old_ref: str | None,
    new_ref: str | None,
    only_if_version_changed: bool,
    include_examples: bool,
    include_placeholders: bool,
    output: list[str],
) -> list[Info]:
    """Return info about directories matching the category, filtered based on the other options.

    Args:
        category: What to iterate over -- 'packages' or 'interfaces'.
        old_ref: git reference to diff with.
            If `None`, no diff is performed.
            Otherwiseonly changed items are returned.
        new_ref: if old_ref is not `None`, diff it with new_ref.
            If this new_ref is `None`, old_ref is diffed with the current state on disk.
        only_if_version_changed: Only output items that have had a version bump.
            Only respected if `refs` are provided.
        include_examples: Whether to include the example libraries.
            Typically included for testing, but excluded from docs and publishing.
        include_placeholders: Whether to include the namespace placeholder packages.
            Typically included for testing and publishing, but excluded from docs.
        output: List of fields to include in the output, one or more of
            'name', 'path', or 'version'
    """
    include: list[str] = []
    if include_examples:
        include.extend(('.example', '.tutorial'))
    if include_placeholders:
        include.append('.package')
    with _snapshot_repo(new_ref) as root:
        # Collect packages or interfaces.
        if category == 'packages':
            dirs = _packages(root, include=include)
        elif category == 'interfaces':
            dirs = _interfaces(root, include=include)
        else:
            raise ValueError(f'Unknown value for `category` {category!r}')
        # Filter based on changes.
        # Return full info if we calculate it.
        if old_ref:
            dirs = _changed_only(root, dirs, ref=old_ref)
            if only_if_version_changed:
                return _get_changed_version_info(category, root, dirs, ref=old_ref)
        # Otherwise calculate only the information needed.
        infos: list[Info] = []
        for path in dirs:
            if not (root / path).exists():
                continue
            if 'version' in output:
                info = _get_info(category, root, path)
                assert info is not None  # we already skipped if the path doesn't exist
            elif 'name' in output:
                info = Info(path=str(path), name=_get_name(category, root, path))
            else:
                info = Info(path=str(path))
            infos.append(info)
        return infos


def _packages(root: pathlib.Path, include: list[str]) -> list[pathlib.Path]:
    """Iterate over package directories in the repository.

    Returns any directory starting with [a-z] from the root and from the 'interfaces'
    sub-directory, as well as any directories listed in `include`, if they exists and have a
    'pyproject.toml' file with a 'project' table.
    """
    paths: set[pathlib.Path] = set()
    for r in root, root / 'interfaces':
        paths.update(r.glob(r'[a-z]*'))
        paths.update(r / i for i in include)
    return sorted(path.relative_to(root) for path in paths if _is_package(path))


def _is_package(path: pathlib.Path) -> bool:
    """Return whether path points to a Python package."""
    pyproject_toml = path / 'pyproject.toml'
    if not pyproject_toml.exists():
        return False
    return 'project' in tomllib.loads(pyproject_toml.read_text())


def _interfaces(root: pathlib.Path, include: list[str]) -> list[pathlib.Path]:
    """Iterate over interface directories in the repository.

    Returns any directory starting with [a-z] from the interfaces sub-directory, as well as any
    directories listed in `include`, if they exist and have an 'interface' subdirectory.
    """
    interfaces_root = root / 'interfaces'
    paths: set[pathlib.Path] = {*interfaces_root.glob(r'[a-z]*')}
    paths.update(interfaces_root / path for path in include)
    return sorted(path.relative_to(root) for path in paths if _is_interface(path))


def _is_interface(path: pathlib.Path) -> bool:
    """Return whether path points to a directory containing an interface definition."""
    return (path / 'interface').is_dir()


def _changed_only(root: pathlib.Path, dirs: list[pathlib.Path], ref: str) -> list[pathlib.Path]:
    """Return only those `dirs` that have changed between `ref` and current state on disk.

    Untracked files are included as changes.
    Calls `git diff` and `git ls-files` once each.
    """
    cmd = ['git', 'diff', '--name-only', ref]
    names = subprocess.check_output(cmd, text=True).strip().splitlines()
    # Include untracked files (for running locally).
    cmd = ['git', 'ls-files', '--others', '--exclude-standard']
    names.extend(subprocess.check_output(cmd, text=True).strip().splitlines())
    # Make set of all top-level and one-level-deep parents of changes.
    # e.g. [foo/bar/baz/bartholemew] -> {foo, foo/bar}
    changes: set[pathlib.Path] = set()
    for name in names:
        parts = pathlib.Path(name).parts
        changes.add(pathlib.Path(parts[0]))
        changes.add(pathlib.Path(*parts[:2]))
    return [p for p in dirs if p in changes]


def _get_changed_version_info(
    category: str, root: pathlib.Path, dirs: list[pathlib.Path], ref: str
) -> list[Info]:
    """Returns only those packages that have had a version change between `ref` and current state.

    Takes a snapshot of the repo at `ref` for comparison.
    Excludes changes where the new version is a dev version.
    """
    with _snapshot_repo(ref) as old_root:
        old_versions: dict[str, str] = {}
        for path in dirs:
            info = _get_info(category, old_root, path)
            if info is not None:
                old_versions[info.name] = info.version
    infos: list[Info] = []
    for path in dirs:
        info = _get_info(category, root, path)
        if info is None:
            logger.debug('%s no longer exists!', path)
            continue
        old_version = old_versions.get(info.name)
        logger.info('%s (%s): %s -> %s', info.path, info.name, old_version, info.version)
        if info.version == old_version:
            logger.debug('Version unchanged')
        elif 'dev' in info.version:
            logger.debug('Skipping dev release.')
        else:
            infos.append(info)
    return infos


@contextlib.contextmanager
def _snapshot_repo(ref: str | None):
    """Yield a snapshot of the current repository at the specified reference in a temp dir.

    If `ref` is `None`, yield the current repository root instead.
    """
    if ref is None:
        yield _REPO_ROOT
        return
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        git = subprocess.run(['git', 'archive', ref], stdout=subprocess.PIPE, check=True)
        stream = io.BytesIO(git.stdout)
        with tarfile.open(fileobj=stream) as tar:
            tar.extractall(path=root)  # noqa: S202
        yield root


def _get_info(category: str, root: pathlib.Path, path: pathlib.Path | str) -> Info | None:
    """Return info for `root / package`, or `None` if it doesn't exist."""
    if not (root / path).exists():
        return None
    logger.debug('Computing version for %s', path)
    name = _get_name(category, root, path)
    if category == 'packages':
        script = f'import importlib.metadata; print(importlib.metadata.version("{name}"))'
        cmd = ['uv', 'run', '--no-project', '--with', f'./{path}', 'python', '-c', script]
        version = subprocess.check_output(cmd, cwd=root, text=True).strip()
    else:
        assert category == 'interfaces'
        version = max((root / path / 'interface').glob('v[0-9]*')).name
    info = Info(path=str(path), name=name, version=version)
    logger.debug('Computed %s', info)
    return info


def _get_name(category: str, root: pathlib.Path, path: pathlib.Path | str) -> str:
    """Return package or interface name."""
    if category == 'packages':
        return _get_dist_name(root / path)
    assert category == 'interfaces'
    return (root / path).name


def _get_dist_name(package: pathlib.Path) -> str:
    """Load distribution package name from pyproject.toml and normalize it."""
    with (package / 'pyproject.toml').open('rb') as f:
        return _normalize(tomllib.load(f)['project']['name'])


def _normalize(name: str) -> str:
    """Normalize distribution package name according to PyPI rules.

    https://packaging.python.org/en/latest/specifications/name-normalization/#name-normalization
    """
    return re.sub(r'[-_.]+', '-', name).lower()


if __name__ == '__main__':
    _main()
