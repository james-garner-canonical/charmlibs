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


# --- _normalize ---


@pytest.mark.parametrize(
    ('name', 'expected'),
    [
        ('tls-certificates', 'tls-certificates'),
        ('certificate_transfer', 'certificate-transfer'),
        ('nginx_k8s', 'nginx-k8s'),
    ],
)
def test_normalize(name: str, expected: str):
    assert pp._normalize(name) == expected


# --- _build_sphinx_map ---


def test_build_sphinx_map_tutorial(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Tutorial files appear in the sphinx map."""
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    monkeypatch.setattr(pp, '_DOCS_DIR', tmp_path / '.docs')
    (tmp_path / '.docs').mkdir()
    lib_docs = tmp_path / 'mylib' / 'docs'
    lib_docs.mkdir(parents=True)
    (lib_docs / 'tutorial.md').touch()
    m = pp._build_sphinx_map(['mylib'])
    assert m['mylib/docs/tutorial.md'] == '/tutorials/charmlibs/mylib'


def test_build_sphinx_map_interface_version_readme(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Interface version READMEs map to /reference/interfaces/{name}/v{N}."""
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    monkeypatch.setattr(pp, '_DOCS_DIR', tmp_path / '.docs')
    (tmp_path / '.docs').mkdir()
    v1_dir = tmp_path / 'interfaces' / 'tls-certificates' / 'interface' / 'v1'
    v1_dir.mkdir(parents=True)
    (v1_dir / 'README.md').touch()
    m = pp._build_sphinx_map(['interfaces/tls-certificates'])
    assert m['interfaces/tls-certificates/interface/v1/README.md'] == '/reference/interfaces/tls-certificates/v1'


def test_build_sphinx_map_package_readme(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Package READMEs map to /reference/charmlibs/{normalized-name}."""
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    monkeypatch.setattr(pp, '_DOCS_DIR', tmp_path / '.docs')
    (tmp_path / '.docs').mkdir()
    m = pp._build_sphinx_map(['pathops'])
    assert m['pathops/README.md'] == '/reference/charmlibs/pathops'


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


# --- _rewrite_links ---


def test_rewrite_links_known_doc(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Relative link to a file in the sphinx map becomes a Sphinx path."""
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    source = tmp_path / 'pkg' / 'docs' / 'tutorial.md'
    source.parent.mkdir(parents=True)
    # Target file must exist for resolve() to produce a consistent path.
    target = tmp_path / 'pkg' / 'docs' / 'how-to' / 'deploy.md'
    target.parent.mkdir(parents=True)
    target.touch()
    sphinx_map = {'pkg/docs/how-to/deploy.md': '/how-to/charmlibs/pkg/deploy'}
    content = 'See [guide](how-to/deploy.md) for details.'
    result = pp._rewrite_links(content, source, sphinx_map)
    assert result == 'See [guide](/how-to/charmlibs/pkg/deploy) for details.'


def test_rewrite_links_with_anchor(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Anchors are preserved after rewriting."""
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    source = tmp_path / 'pkg' / 'docs' / 'tutorial.md'
    source.parent.mkdir(parents=True)
    target = tmp_path / 'pkg' / 'docs' / 'how-to' / 'deploy.md'
    target.parent.mkdir(parents=True)
    target.touch()
    sphinx_map = {'pkg/docs/how-to/deploy.md': '/how-to/charmlibs/pkg/deploy'}
    content = 'See [step 2](how-to/deploy.md#step-2).'
    result = pp._rewrite_links(content, source, sphinx_map)
    assert result == 'See [step 2](/how-to/charmlibs/pkg/deploy#step-2).'


def test_rewrite_links_unknown_file_github(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Relative link to a non-doc file falls back to GitHub URL."""
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    monkeypatch.setattr(pp, '_REPO_MAIN_URL', 'https://github.com/canonical/charmlibs/blob/main')
    source = tmp_path / 'pkg' / 'docs' / 'tutorial.md'
    source.parent.mkdir(parents=True)
    target = tmp_path / 'pkg' / 'src' / 'mod.py'
    target.parent.mkdir(parents=True)
    target.touch()
    content = 'See [source](../src/mod.py).'
    result = pp._rewrite_links(content, source, {})
    assert 'https://github.com/canonical/charmlibs/blob/main/pkg/src/mod.py' in result


def test_rewrite_links_preserves_http():
    """Absolute HTTP(S) links are left unchanged."""
    content = 'See [docs](https://example.com/page) for details.'
    result = pp._rewrite_links(content, pathlib.Path('/fake/source.md'), {})
    assert result == content


def test_rewrite_links_image_github(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Image links to non-doc files fall back to GitHub URL."""
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    monkeypatch.setattr(pp, '_REPO_MAIN_URL', 'https://github.com/canonical/charmlibs/blob/main')
    source = tmp_path / 'pkg' / 'docs' / 'tutorial.md'
    source.parent.mkdir(parents=True)
    target = tmp_path / 'pkg' / 'docs' / 'images' / 'arch.png'
    target.parent.mkdir(parents=True)
    target.touch()
    content = '![diagram](images/arch.png)'
    result = pp._rewrite_links(content, source, {})
    assert 'https://github.com/canonical/charmlibs/blob/main/pkg/docs/images/arch.png' in result


def test_rewrite_links_outside_repo_raises(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Link resolving outside the repo root raises ValueError."""
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path / 'repo')
    source = tmp_path / 'repo' / 'pkg' / 'docs' / 'tutorial.md'
    source.parent.mkdir(parents=True)
    content = 'See [bad](../../../../etc/passwd).'
    with pytest.raises(ValueError, match='resolves outside the repo'):
        pp._rewrite_links(content, source, {})


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
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    entry = pp._copy_tutorial(lib_docs, 'mylib', False, {})
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
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    entry = pp._copy_tutorial(lib_docs, 'tls-certs', True, {})
    out = docs_dir / 'tutorials' / 'charmlibs' / 'interfaces' / 'tls-certs.md'
    assert out.exists()
    assert entry == 'tls-certs: Tutorial <charmlibs/interfaces/tls-certs>'


def test_copy_tutorial_no_file(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    docs_dir = tmp_path / 'docs_site'
    lib_docs = tmp_path / 'lib' / 'docs'
    lib_docs.mkdir(parents=True)
    monkeypatch.setattr(pp, '_DOCS_DIR', docs_dir)
    entry = pp._copy_tutorial(lib_docs, 'mylib', False, {})
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
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    entries = pp._copy_category(lib_docs, 'mylib', False, 'how-to', {})
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
    monkeypatch.setattr(pp, '_REPO_ROOT', tmp_path)
    entries = pp._copy_category(lib_docs, 'tls-certs', True, 'explanation', {})
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
    entries = pp._copy_category(lib_docs, 'mylib', False, 'how-to', {})
    assert entries == []


def test_copy_category_no_dir(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    docs_dir = tmp_path / 'docs_site'
    lib_docs = tmp_path / 'lib' / 'docs'
    lib_docs.mkdir(parents=True)
    monkeypatch.setattr(pp, '_DOCS_DIR', docs_dir)
    entries = pp._copy_category(lib_docs, 'mylib', False, 'how-to', {})
    assert entries == []
