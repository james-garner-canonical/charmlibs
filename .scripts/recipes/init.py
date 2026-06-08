#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.12"
# dependencies = []
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

"""Scaffold a new charmlibs package interactively (forwards extra args to cookiecutter)."""

from __future__ import annotations

import argparse
import os
import sys

import _common


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    _, cookiecutter_args = parser.parse_known_args()
    bold, normal, cyan = '\033[1m', '\033[0m', '\033[36m'
    print(
        f'✨{bold}IMPORTANT{normal}✨ The project name should be the import package name,'
        f' without the {cyan}charmlibs.{normal} namespace.'
    )
    print('You can press enter to accept the default, shown in brackets.')
    template = _common.REPO_ROOT / '.template'
    env = {**os.environ, 'CHARMLIBS_TEMPLATE': str(template.resolve())}
    cmd = ['uvx', 'cookiecutter', '.template', *cookiecutter_args]
    sys.exit(_common.run(cmd, env=env))


if __name__ == '__main__':
    _main()
