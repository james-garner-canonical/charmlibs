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

import argparse
import json
import logging
import pathlib
import subprocess

import yaml

_REPO_ROOT = pathlib.Path(__file__).parent.parent

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(str(pathlib.Path(__file__).relative_to(_REPO_ROOT)))


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('git_base_ref', nargs='?', default='')
    parser.add_argument('--only-those-with-tests', action='store_true')
    args = parser.parse_args()
    targets = _get_interface_test_targets(
        args.git_base_ref, has_tests_only=args.only_those_with_tests
    )
    output = json.dumps(targets)
    logger.info(output)
    print(output)


def _get_interface_test_targets(git_base_ref: str, has_tests_only: bool) -> list[dict[str, str]]:
    cmd = ['.scripts/ls.py', 'interfaces']
    if git_base_ref:
        cmd.append(git_base_ref)
    interfaces = json.loads(subprocess.check_output(cmd, text=True).strip())
    targets: list[dict[str, str]] = []
    for i in interfaces:
        interface = _REPO_ROOT / i
        for v in sorted((interface / 'interface').glob('v[0-9]*')):
            interface_yaml = yaml.safe_load((v / 'interface.yaml').read_text())
            for role in 'provide', 'require':
                charms = interface_yaml.get(f'{role}rs', [])
                if not charms:
                    logger.debug('No charms for %s %s %s role.', interface.name, v.name, role)
                    continue
                if has_tests_only and not (v / 'tests' / 'test_{role}.py').exists():
                    msg = 'Skipping these charms because there are no tests for %s: %s'
                    logger.warning(msg, role, charms)
                    continue
                targets.extend([
                    {
                        'interface': interface.name,
                        'version': v.name,
                        'role': role,
                        'charm_name': c['name'],
                        'charm_repo': c['url'],
                        'charm_ref': c.get('branch', 'main'),
                    }
                    for c in charms
                ])
    return targets


if __name__ == '__main__':
    _main()
