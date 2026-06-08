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

"""Shared implementation for the `pack-k8s` and `pack-machine` recipes."""

from __future__ import annotations

import argparse
import os
import sys

import _common


def main(argv: list[str]) -> None:
    """Pack the package's integration-test charm(s) for the substrate selected in `argv`.

    The thin wrapper recipe passes exactly one of `--k8s` / `--machine` to select the substrate.
    """
    parser = argparse.ArgumentParser()
    substrate = parser.add_mutually_exclusive_group(required=True)
    substrate.add_argument('--k8s', dest='substrate', action='store_const', const='k8s')
    substrate.add_argument('--machine', dest='substrate', action='store_const', const='machine')
    parser.add_argument(
        '--tag',
        default=os.environ.get('CHARMLIBS_TAG', ''),
        help='Value for the CHARMLIBS_TAG environment var (defaults to $CHARMLIBS_TAG).',
    )
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    args, pack_args = parser.parse_known_args(argv)
    integration_dir = _common.REPO_ROOT / args.package / 'tests' / 'integration'
    env = {**os.environ, 'CHARMLIBS_SUBSTRATE': args.substrate, 'CHARMLIBS_TAG': args.tag}
    sys.exit(_common.run(['./pack.sh', *pack_args], cwd=integration_dir, env=env))
