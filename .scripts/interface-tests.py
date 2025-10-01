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

"""Run interface tests for the specified target.

The interface name and version, and the charm's role and name must all be provided as CLI args.

For example: .scripts/interface-tests.py tracing v2 provider tempo-coordinator-k8s
"""

import argparse
import logging
import os
import pathlib
import subprocess
import sys
import tempfile

import yaml

_REPO_ROOT = pathlib.Path(__file__).parent.parent
_INTERFACES = _REPO_ROOT / 'interfaces'
_TEST_CONTENT = """
# auto-generated test file

from interface_tester import InterfaceTester


def test_{interface}_interface({fixture_id}: InterfaceTester):
    {fixture_id}.configure(
        interface_name="{interface}",
        interface_version={version},
        repo="{repo}",
        branch="{branch}",
    )
    {fixture_id}.run()
""".strip()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(str(pathlib.Path(__file__).relative_to(_REPO_ROOT)))


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('name')
    parser.add_argument('version')
    parser.add_argument('role', choices=('provide', 'require'))
    parser.add_argument('charm_name', nargs='?')
    parser.add_argument('--charm-repo')
    parser.add_argument('--charm-ref')
    parser.add_argument('--charmlibs-repo')
    parser.add_argument('--charmlibs-ref')
    args = parser.parse_args()
    returncode = _interface_tests(
        interface_name=args.name,
        interface_version=args.version,
        role=args.role,
        charm_name=args.charm_name,
        charm_repo=args.charm_repo,
        charm_ref=args.charm_ref,
        charmlibs_repo=args.charmlibs_repo,
        charmlibs_ref=args.charmlibs_ref,
    )
    sys.exit(returncode)


def _interface_tests(
    interface_name: str,
    interface_version: str,
    role: str,
    charm_name: str,
    charm_repo: str | None,
    charm_ref: str | None,
    charmlibs_repo: str | None,
    charmlibs_ref: str | None,
) -> int:
    # load charm and test config if it exists
    interface_dir = _INTERFACES / interface_name / 'interface' / interface_version
    charms = yaml.safe_load((interface_dir / 'interface.yaml').read_text())[f'{role}rs']
    [charm_config] = [c for c in charms if c['name'] == charm_name] or [{}]
    logger.info('Charm config: %s', charm_config)
    test_config = charm_config.get('test_setup', {})
    # write and execute interface tester file in cloned charm repo
    with tempfile.TemporaryDirectory() as td:
        repo_path = pathlib.Path(td, 'charm-repo')
        # clone charm repo
        git_clone = ['git', 'clone', '--depth', '1']
        if branch := charm_ref or charm_config.get('branch'):
            git_clone.extend(['--branch', branch])
        git_clone.extend([charm_repo or charm_config['url'], repo_path])
        logger.info(git_clone)
        subprocess.check_call(git_clone, cwd=td)
        # write interface test file
        content = _TEST_CONTENT.format(
            interface=interface_name,
            version=interface_version.removeprefix('v'),
            repo=charmlibs_repo or _REPO_ROOT,
            branch=charmlibs_ref or _current_branch(),
            fixture_id=test_config.get('identifier', 'interface_tester'),
        )
        charm_root = repo_path / test_config.get('charm_root', '')
        test_file = pathlib.Path(
            test_config.get('location', 'tests/interface_tests/conftest.py')
        ).parent / f'test_{role}s_{interface_name}_{interface_version}.py'
        (charm_root / test_file).write_text(content)
        # execute interface tests
        if pre_run := test_config.get('pre_run'):
            logger.info(pre_run)
            subprocess.check_call(pre_run, shell=True, cwd=charm_root)
        pytest = [
            'uv',
            'tool',
            'run',
            '--with=setuptools',
            '--with=pytest-interface-tester',
            '--with-requirements=requirements.txt',
            'pytest',
            test_file,
        ]
        logger.info(pytest)
        proc = subprocess.run(pytest, env={**os.environ, 'PYTHONPATH': 'src:lib'}, cwd=charm_root)
        return proc.returncode


def _current_branch() -> str:
    cmd = ['git', 'branch', '--show-current']
    return subprocess.check_output(cmd, text=True, cwd=_REPO_ROOT).strip()


if __name__ == '__main__':
    _main()
