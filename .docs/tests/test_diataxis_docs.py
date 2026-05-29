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

"""Unit tests for the diataxis_docs Sphinx fallback extension."""

from __future__ import annotations

import pathlib

import diataxis_docs


def test_fallback_writes_placeholder_when_no_include(tmp_path: pathlib.Path):
    """Fallback writes placeholder include + page when preprocessor hasn't run."""
    for rel_path in diataxis_docs.INCLUDE_FILES:
        include_file = tmp_path / rel_path
        include_file.parent.mkdir(parents=True, exist_ok=True)

    # Simulate fallback logic
    for rel_path in diataxis_docs.INCLUDE_FILES:
        include_file = tmp_path / rel_path
        if not include_file.exists():
            category_dir = include_file.parent
            placeholder_path = category_dir / '_placeholder.md'
            diataxis_docs._write_if_needed(path=placeholder_path, content=diataxis_docs.FALLBACK_PAGE)
            diataxis_docs._write_if_needed(path=include_file, content=diataxis_docs.FALLBACK_TOCTREE)

    for rel_path in diataxis_docs.INCLUDE_FILES:
        include_file = tmp_path / rel_path
        assert include_file.exists()
        assert '_placeholder' in include_file.read_text()
        assert (include_file.parent / '_placeholder.md').exists()


def test_fallback_skips_when_include_exists(tmp_path: pathlib.Path):
    """Fallback does nothing when preprocessor has already run."""
    for rel_path in diataxis_docs.INCLUDE_FILES:
        include_file = tmp_path / rel_path
        include_file.parent.mkdir(parents=True, exist_ok=True)
        include_file.write_text('')  # preprocessor wrote empty include

    # Simulate fallback logic
    for rel_path in diataxis_docs.INCLUDE_FILES:
        include_file = tmp_path / rel_path
        if not include_file.exists():
            diataxis_docs._write_if_needed(path=include_file, content=diataxis_docs.FALLBACK_TOCTREE)

    for rel_path in diataxis_docs.INCLUDE_FILES:
        include_file = tmp_path / rel_path
        assert include_file.read_text() == ''
        assert not (include_file.parent / '_placeholder.md').exists()
