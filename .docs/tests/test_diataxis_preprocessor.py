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

"""Unit tests for the diataxis preprocessor script."""

from __future__ import annotations

import pathlib

import diataxis_preprocessor as pp
import pytest


# --- _lib_name ---


@pytest.mark.parametrize(
    ('raw_package', 'expected'),
    [
        ('pathops', 'pathops'),
        ('interfaces/tls-certificates', 'tls-certificates'),
        ('interfaces/certificate_transfer', 'certificate_transfer'),
    ],
)
def test_lib_name(raw_package: str, expected: str):
    assert pp._lib_name(raw_package) == expected


# --- _extract_h1 ---


def test_extract_h1_md():
    assert pp._extract_h1('# Getting Started\n\nText.\n', '.md') == 'Getting Started'


def test_extract_h1_md_no_heading():
    assert pp._extract_h1('No heading here.\n', '.md') == 'Untitled'


def test_extract_h1_rst():
    assert pp._extract_h1('My Title\n========\n\nText.\n', '.rst') == 'My Title'


# --- _prefix_h1 ---


def test_prefix_h1_md():
    content = '# Getting Started\n\nSome text.\n'
    result = pp._prefix_h1(content, 'tls-certificates', '.md')
    assert result.startswith('# tls-certificates: Getting Started\n')


def test_prefix_h1_md_preserves_rest():
    content = '# Title\n\n## Subtitle\n\nBody.\n'
    result = pp._prefix_h1(content, 'mylib', '.md')
    assert result == '# mylib: Title\n\n## Subtitle\n\nBody.\n'


def test_prefix_h1_md_only_first():
    content = '# First\n\n# Second\n'
    result = pp._prefix_h1(content, 'lib', '.md')
    assert result == '# lib: First\n\n# Second\n'


def test_prefix_h1_rst():
    content = 'Getting Started\n================\n\nSome text.\n'
    result = pp._prefix_h1(content, 'tls-certificates', '.rst')
    expected_title = 'tls-certificates: Getting Started'
    lines = result.split('\n')
    assert lines[0] == expected_title
    assert lines[1] == '=' * len(expected_title)


# --- _rewrite_relative_links ---


def test_rewrite_relative_links():
    content = 'See [guide](how-to/deploy.md) for details.'
    base_url = 'https://github.com/canonical/charmlibs/blob/main/pathops/docs'
    result = pp._rewrite_relative_links(content, base_url)
    assert result == f'See [guide]({base_url}/how-to/deploy.md) for details.'


def test_rewrite_relative_links_preserves_http():
    content = 'See [docs](https://example.com/page) for details.'
    result = pp._rewrite_relative_links(content, 'https://github.com/x')
    assert result == content


def test_rewrite_relative_links_image():
    content = '![diagram](images/arch.png)'
    base_url = 'https://github.com/canonical/charmlibs/blob/main/pkg/docs'
    result = pp._rewrite_relative_links(content, base_url)
    assert f'{base_url}/images/arch.png' in result


# --- _write_if_needed ---


def test_write_if_needed_creates(tmp_path: pathlib.Path):
    path = tmp_path / 'test.md'
    pp._write_if_needed(path=path, content='# Hello\n')
    assert path.read_text() == '# Hello\n'


def test_write_if_needed_skips_unchanged(tmp_path: pathlib.Path):
    path = tmp_path / 'test.md'
    path.write_text('# Hello\n')
    mtime_before = path.stat().st_mtime_ns
    pp._write_if_needed(path=path, content='# Hello\n')
    assert path.stat().st_mtime_ns == mtime_before


def test_write_if_needed_overwrites_changed(tmp_path: pathlib.Path):
    path = tmp_path / 'test.md'
    path.write_text('# Old\n')
    pp._write_if_needed(path=path, content='# New\n')
    assert path.read_text() == '# New\n'


# --- _write_include ---


def test_write_include_with_entries(tmp_path: pathlib.Path):
    path = tmp_path / '_lib-tutorials.md'
    pp._write_include(path, ['tls-certificates: Tutorial <charmlibs/interfaces/tls-certificates>'])
    content = path.read_text()
    assert '```{toctree}' in content
    assert 'tls-certificates: Tutorial <charmlibs/interfaces/tls-certificates>' in content


def test_write_include_empty(tmp_path: pathlib.Path):
    path = tmp_path / '_lib-tutorials.md'
    pp._write_include(path, [])
    assert path.read_text() == ''


# --- _copy_tutorial ---


def test_copy_tutorial_md(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    docs_dir = tmp_path / 'docs_site'
    lib_docs = tmp_path / 'lib' / 'docs'
    lib_docs.mkdir(parents=True)
    (lib_docs / 'tutorial.md').write_text('# My Tutorial\n\nContent.\n')
    monkeypatch.setattr(pp, '_DOCS_DIR', docs_dir)
    entry = pp._copy_tutorial(lib_docs, 'mylib', False, 'https://gh/mylib/docs')
    out = docs_dir / 'tutorials' / 'charmlibs' / 'mylib.md'
    assert out.exists()
    assert out.read_text().startswith('# mylib: My Tutorial\n')
    assert entry == 'mylib: My Tutorial <charmlibs/mylib>'


def test_copy_tutorial_interface(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    docs_dir = tmp_path / 'docs_site'
    lib_docs = tmp_path / 'lib' / 'docs'
    lib_docs.mkdir(parents=True)
    (lib_docs / 'tutorial.md').write_text('# Tutorial\n')
    monkeypatch.setattr(pp, '_DOCS_DIR', docs_dir)
    entry = pp._copy_tutorial(lib_docs, 'tls-certs', True, 'https://gh/docs')
    out = docs_dir / 'tutorials' / 'charmlibs' / 'interfaces' / 'tls-certs.md'
    assert out.exists()
    assert entry == 'tls-certs: Tutorial <charmlibs/interfaces/tls-certs>'


def test_copy_tutorial_no_file(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    docs_dir = tmp_path / 'docs_site'
    lib_docs = tmp_path / 'lib' / 'docs'
    lib_docs.mkdir(parents=True)
    monkeypatch.setattr(pp, '_DOCS_DIR', docs_dir)
    entry = pp._copy_tutorial(lib_docs, 'mylib', False, 'https://gh/docs')
    assert entry is None
    assert not (docs_dir / 'tutorials').exists()


# --- _copy_category ---


def test_copy_category(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    docs_dir = tmp_path / 'docs_site'
    lib_docs = tmp_path / 'lib' / 'docs'
    howto_dir = lib_docs / 'how-to'
    howto_dir.mkdir(parents=True)
    (howto_dir / 'deploy.md').write_text('# Deploy\n\nSteps.\n')
    (howto_dir / 'upgrade.md').write_text('# Upgrade\n\nSteps.\n')
    monkeypatch.setattr(pp, '_DOCS_DIR', docs_dir)
    entries = pp._copy_category(lib_docs, 'mylib', False, 'https://gh/docs', 'how-to')
    out_dir = docs_dir / 'how-to' / 'charmlibs' / 'mylib'
    assert (out_dir / 'deploy.md').exists()
    assert (out_dir / 'upgrade.md').exists()
    assert (out_dir / 'deploy.md').read_text().startswith('# mylib: Deploy\n')
    assert len(entries) == 2
    assert 'mylib: Deploy <charmlibs/mylib/deploy>' in entries


def test_copy_category_interface(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    docs_dir = tmp_path / 'docs_site'
    lib_docs = tmp_path / 'lib' / 'docs'
    expl_dir = lib_docs / 'explanation'
    expl_dir.mkdir(parents=True)
    (expl_dir / 'security.md').write_text('# Security\n')
    monkeypatch.setattr(pp, '_DOCS_DIR', docs_dir)
    entries = pp._copy_category(lib_docs, 'tls-certs', True, 'https://gh/docs', 'explanation')
    out = docs_dir / 'explanation' / 'charmlibs' / 'interfaces' / 'tls-certs' / 'security.md'
    assert out.exists()
    assert entries == ['tls-certs: Security <charmlibs/interfaces/tls-certs/security>']


def test_copy_category_skips_non_md(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    docs_dir = tmp_path / 'docs_site'
    lib_docs = tmp_path / 'lib' / 'docs'
    howto_dir = lib_docs / 'how-to'
    howto_dir.mkdir(parents=True)
    (howto_dir / 'notes.txt').write_text('not a doc')
    monkeypatch.setattr(pp, '_DOCS_DIR', docs_dir)
    entries = pp._copy_category(lib_docs, 'mylib', False, 'https://gh/docs', 'how-to')
    assert entries == []


def test_copy_category_no_dir(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    docs_dir = tmp_path / 'docs_site'
    lib_docs = tmp_path / 'lib' / 'docs'
    lib_docs.mkdir(parents=True)
    monkeypatch.setattr(pp, '_DOCS_DIR', docs_dir)
    entries = pp._copy_category(lib_docs, 'mylib', False, 'https://gh/docs', 'how-to')
    assert entries == []
