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

# BEGIN: contents of {tests_path}

{tests_content}

# END: contents of {tests_path}

import contextlib

import interface_tester
import pytest


@pytest.fixture(scope="function", autouse=True)
def test_{interface}_interface(
    {fixture_id}: interface_tester.InterfaceTester,
    request: pytest.FixtureRequest,
):
    {fixture_id}.configure(
        interface_name="{interface}",
        interface_version={version},
        repo="{repo}",
        branch="{branch}",
        interface_subdir="interface",
        tests_dir="tests",
    )
    role = "{role}"
    import schema
    role_schema = getattr(schema, role.capitalize() + "Schema")
    class Cleanup(Exception):
        '''Exception to trigger context cleanup.'''
    with contextlib.suppress(Cleanup):
        with {fixture_id}.context(
            test_fn=request.function,
            role=role,
            schema=role_schema,
            endpoint="{endpoint}",
        ):
            yield
            if getattr(request.node, 'report').failed:
                raise Cleanup()
""".strip()
_PLUGIN_MODULE = 'report_plugin'
_PLUGIN_CONTENT = """
import pytest

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    print(type(outcome), outcome)
    report = outcome.get_result()
    if report.when == "call":
        setattr(item, "report", report)
""".strip()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(str(pathlib.Path(__file__).relative_to(_REPO_ROOT)))


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('name')
    parser.add_argument('version')
    parser.add_argument('role', choices=('provide', 'require'))
    parser.add_argument('charm_name')
    parser.add_argument('endpoint')
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
        endpoint=args.endpoint,
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
    endpoint: str,
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
    if not charm_config:
        assert charm_repo, f'--charm-repo is required as there is no config for {charm_name}.'
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
        interface_tests_path = pathlib.Path(interface_dir, 'tests',  f'test_{role}r.py')
        charm_test_content = _TEST_CONTENT.format(
            tests_path=interface_tests_path,
            tests_content=interface_tests_path.read_text(),
            interface=interface_name,
            version=interface_version.removeprefix('v'),
            repo=charmlibs_repo or _REPO_ROOT,
            branch=charmlibs_ref or _current_branch(),
            fixture_id=test_config.get('identifier', 'interface_tester'),
            role=f'{role}r',
            endpoint=endpoint,
        )
        charm_root = repo_path / test_config.get('charm_root', '')
        charm_test_dir = (
            charm_root
            / test_config.get('location', 'tests/interface_tests/conftest.py')
        ).parent
        charm_test_file = charm_test_dir / f'test_{role}s_{interface_name}_{interface_version}.py'
        charm_test_file.write_text(charm_test_content)
        (charm_test_dir / 'schema.py').symlink_to(interface_dir / 'schema.py')
        (charm_root / f'{_PLUGIN_MODULE}.py').write_text(_PLUGIN_CONTENT)
        # execute interface tests
        if pre_run := test_config.get('pre_run'):
            logger.info(pre_run)
            subprocess.check_call(pre_run, shell=True, cwd=charm_root)
        pytest = [
            'uv',
            'tool',
            'run',
            '--with=setuptools',
            '--with=git+https://github.com/james-garner-canonical/pytest-interface-tester@25-09+feat+location-customization-for-charmlibs',
            '--with-requirements=requirements.txt',
            'pytest',
            '-p',
            _PLUGIN_MODULE,
            charm_test_file,
        ]
        logger.info(pytest)
        proc = subprocess.run(pytest, env={**os.environ, 'PYTHONPATH': '.:src:lib'}, cwd=charm_root)
        return proc.returncode


def _current_branch() -> str:
    cmd = ['git', 'branch', '--show-current']
    return subprocess.check_output(cmd, text=True, cwd=_REPO_ROOT).strip()


if __name__ == '__main__':
    _main()
