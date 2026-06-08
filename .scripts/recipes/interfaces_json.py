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

"""Generate `interfaces/index.json` from the interface libraries."""

from __future__ import annotations

import argparse
import sys

import _common

# Columns to include for each interface in the generated index.
_OUTPUTS = [
    'name',
    'version',
    'lib',
    'lib_url',
    'docs_url',
    'summary',
    'description',
    'tags',
    'status',
]


def _main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()  # takes no args, but supports `-h`
    output_file = _common.REPO_ROOT / 'interfaces' / 'index.json'
    cmd = ['.scripts/ls.py', 'interfaces']
    for column in _OUTPUTS:
        cmd += ['--output', column]
    cmd.append('--indent-json')
    with output_file.open('w') as f:
        returncode = _common.run(cmd, stdout=f)
    sys.exit(returncode)


if __name__ == '__main__':
    _main()
