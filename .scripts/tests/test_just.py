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

# ruff: noqa: D103 (function docstrings)

"""Unit tests for the just script."""

import pathlib

import just
import pytest


def test_uv_cmd(tmp_path: pathlib.Path):
    (tmp_path / 'pyproject.toml').write_text("[dependency-groups]\nfoo = []\nbar = []")
    test_reqs = pathlib.Path(__file__).parent.parent.parent / 'test-requirements.txt'
    assert just._uv_cmd([], pkg_dir=tmp_path, python='fakepy', groups=['foo']) == [
        'uv', 'run', '--with-requirements', test_reqs, '--python', 'fakepy', '--group', 'foo'
    ]
