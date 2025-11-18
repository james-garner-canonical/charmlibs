#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "PyYAML",
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

"""Collect the targets for running interface tests for the specified interface.

Only outputs targets that there are test cases for by default.
"""

import argparse
import json
import logging
import pathlib
import re
import subprocess
import tempfile

import yaml

_REPO_ROOT = pathlib.Path(__file__).parent.parent

logger = logging.getLogger(str(pathlib.Path(__file__).relative_to(_REPO_ROOT)))


def _main() -> None:
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser()
    parser.add_argument('interface', help='Path from repo root to specific interface directory.')
    parser.add_argument('--only-charm')
    parser.add_argument('--all', action='store_true', help='Include combinations with no tests.')
    parser.add_argument(
        '--include-interface', action='store_true', help='Include `interface` field in the output.'
    )
    parser.add_argument(
        '--exclude-charm', action='store_true', help='Exclude `charm` field from the output.'
    )
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.WARNING)
    targets = _target_from_interface(
        args.interface,
        has_tests_only=not args.all,
        only_charm=args.only_charm,
        include_interface=args.include_interface,
        include_charm_name=not args.exclude_charm,
    )
    output = json.dumps(targets)
    logger.info(output)
    print(output)


def _target_from_interface(
    interface_str: str,
    has_tests_only: bool,
    only_charm: str | None,
    include_interface: bool,
    include_charm_name: bool,
) -> list[dict[str, str]]:
    """Return a list of interface test targets for this interface.

    Iterates over the interface versions, collects all provider and requirer charms, and clones
    the charms to discover their endpoints.

    Args:
        interface_str: The interface path relative to the repo root, e.g. 'interfaces/tracing'.
        has_tests_only: If true, exclude any targets that don't actually have any tests defined.
        only_charm: If provided, only return targets for that charm.
        include_interface: If true, include an `interface` entry in the output dictionaries.
        include_charm_name: If true, include a `charm` entry in the output dictionaries.

    Returns:
        A list of interface test targets. Each target is a dictionary containing:
            - interface (name) (if include_interface)
            - version (with v prefix)
            - role (provide or require)
            - charm_name (name) (if include_charm_name)
            - endpoint (name)
    """
    interface = _REPO_ROOT / interface_str
    version_dirs = sorted((interface / 'interface').glob('v[0-9]*'))
    if not version_dirs:
        logger.warning('%s does not define any interface versions.', interface_str)
        return []
    targets: list[dict[str, str]] = []
    for v in version_dirs:
        interface_yaml = yaml.safe_load((v / 'interface.yaml').read_text())
        if (disable := v / 'tests' / '.disable').exists():
            msg = 'Targets for %s %s will not be included since %s exists.'
            logger.warning(msg, interface_str, v.name, disable)
            continue
        for role in 'provide', 'require':
            charms = interface_yaml.get(f'{role}rs', [])
            if has_tests_only and not _has_tests(v, f'{role}r'):
                msg = 'Skipping these charms because there are no tests for %s %s %s: %s'
                logger.warning(msg, interface_str, v.name, role, charms)
                continue
            if not charms:
                msg = 'No charms for %s %s %s'
                logger.warning(msg, interface_str, v.name, role)
                continue
            for charm in charms:
                logger.debug('%s %s %s', only_charm, charm['name'], charm)
                if only_charm and charm['name'] != only_charm:
                    continue
                endpoints = _get_endpoints(
                    interface=interface.name,
                    role_key=f'{role}s',
                    charm_repo=charm['url'],
                    charm_ref=charm.get('branch', 'main'),
                    charm_root=charm.get('test_setup', {}).get('charm_root', ''),
                )
                for endpoint in endpoints:
                    target: dict[str, str] = {}
                    if include_interface:
                        target['interface'] = interface.name
                    target['version'] = v.name
                    target['role'] = role
                    if include_charm_name:
                        target['charm_name'] = charm['name']
                    target['endpoint'] = endpoint
                    targets.append(target)
    return targets


def _has_tests(version_dir: pathlib.Path, role: str) -> bool:
    """Return whether the test file exists and seems to contain at least one test.

    We heuristically check for tests by looking for any line starting with 'def test',
    ignoring leading whitespace.
    """
    test_file = version_dir / 'tests' / f'test_{role}.py'
    if not test_file.exists():
        logger.warning('%s does not exist.', test_file.relative_to(_REPO_ROOT))
        return False
    has_tests = bool(re.search(r'^\s*def test', test_file.read_text(), re.MULTILINE))
    if not has_tests:
        msg = '%s exists, but does not seem to have any tests.'
        logger.warning(msg, test_file.relative_to(_REPO_ROOT))
    return has_tests


def _get_endpoints(
    interface: str, role_key: str, charm_repo: str, charm_ref: str | None, charm_root: str
) -> list[str]:
    """Clone the charm repo and return the endpoints for the interface and role."""
    with tempfile.TemporaryDirectory() as td:
        repo_path = pathlib.Path(td, 'charm-repo')
        git_clone: list[str | pathlib.Path] = ['git', 'clone', '--depth', '1']
        if charm_ref:
            git_clone.extend(['--branch', charm_ref])
        git_clone.extend([charm_repo, repo_path])
        logger.info(git_clone)
        subprocess.check_call(git_clone, cwd=td)
        for meta in 'metadata.yaml', 'charmcraft.yaml':
            if (path := repo_path / charm_root / meta).exists():
                text = path.read_text()
                logger.debug('%s:%s\n%s\n', charm_repo, path.relative_to(repo_path), text)
                loaded = yaml.safe_load(text)
                if role_key not in loaded:
                    continue
                endpoints = [e for e, d in loaded[role_key].items() if d['interface'] == interface]
                if endpoints:
                    return endpoints
                raise ValueError(
                    f'{interface} not found in {path}[{role_key}]: {loaded[role_key]}'
                )
            else:
                logger.debug('%s:%s does not exist', charm_repo, path.relative_to(repo_path))
        msg = f'{role_key} {interface} not found in metadata for {charm_repo}@{charm_ref}/{charm_root}'  # noqa: E501
        raise ValueError(msg)


if __name__ == '__main__':
    _main()
