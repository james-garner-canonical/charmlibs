#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.12"
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

"""Copy per-library diataxis docs into the Sphinx source tree.

Walks every package returned by ``.scripts/ls.py``, looks for a ``docs/``
directory, and copies tutorial, how-to, and explanation pages into the
corresponding Sphinx source directories. Generates ``_lib-*.md`` include
files containing toctree entries that the index pages pull in via
``{include}``.

Run from ``just docs``; see ``docs.just`` for the invocation.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
from typing import Any

_DOCS_DIR = pathlib.Path(__file__).parent.parent.resolve()
_REPO_ROOT = _DOCS_DIR.parent
_REPO_MAIN_URL = 'https://github.com/canonical/charmlibs/blob/main'
_TOCTREE_HEADER = """\
```{toctree}
:maxdepth: 1

"""
_TOCTREE_FOOTER = '```\n'


def _main() -> None:
    """Discover packages and copy their docs into the Sphinx source tree."""
    cmd = [
        _REPO_ROOT / '.scripts' / 'ls.py',
        'packages',
        '--exclude-examples',
        '--exclude-placeholders',
        '--exclude-testing',
        '--output', 'path',
        '--output', 'docs',
    ]
    packages: list[dict[str, Any]] = json.loads(subprocess.check_output(cmd, text=True))
    sphinx_map = _build_sphinx_map(packages)
    # Copy each package's docs and collect toctree entries for each category.
    all_entries: dict[str, list[str]] = {}
    for pkg in packages:
        lib_path = pathlib.PurePath(pkg['path'])
        docs: dict[str, list[str]] = pkg.get('docs', {})
        for category, doc_files in docs.items():
            sources = [_REPO_ROOT / lib_path / f for f in doc_files]
            entries = _copy_category(sources, lib_path, category, sphinx_map)
            all_entries.setdefault(category, []).extend(entries)
    # Write include files with toctree entries for each category.
    for category, entries in all_entries.items():
        if not entries:
            continue
        path = _DOCS_DIR / category / f'_lib-{category}.md'
        content = _TOCTREE_HEADER + '\n'.join(entries) + '\n' + _TOCTREE_FOOTER
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def _copy_category(
    sources: list[pathlib.Path],
    lib_path: pathlib.PurePath,
    category: str,
    sphinx_map: dict[pathlib.PurePath, str],
) -> list[str]:
    """Copy a library's docs for one category and return toctree entries."""
    if not sources:
        return []
    out_dir = _DOCS_DIR / category / 'charmlibs' / lib_path
    out_dir.mkdir(parents=True, exist_ok=True)
    entries: list[str] = []
    for source in sources:
        content = source.read_text()
        title = _extract_h1(content, source.suffix)
        content = _prefix_h1(content, lib_path.name, source.suffix)
        content = _rewrite_links(content, source, sphinx_map)
        (out_dir / source.name).write_text(content)
        entries.append(f'{lib_path.name}: {title} <charmlibs/{lib_path}/{source.stem}>')
    return entries


def _extract_h1(content: str, ext: str) -> str:
    """Extract the first H1 heading text from content."""
    if ext == '.md':
        match = re.search(r'^# (.+)$', content, re.MULTILINE)
        return match.group(1).strip() if match else 'Untitled'
    lines = content.split('\n')
    i = _rst_title_index(lines)
    return lines[i].strip() if i is not None else 'Untitled'


def _prefix_h1(content: str, lib_name: str, ext: str) -> str:
    """Prepend the library name to the first H1 heading."""
    if ext == '.md':
        return re.sub(r'^(# )', rf'\1{lib_name}: ', content, count=1, flags=re.MULTILINE)
    lines = content.split('\n')
    i = _rst_title_index(lines)
    if i is not None:
        lines[i] = f'{lib_name}: {lines[i]}'
        lines[i + 1] = lines[i + 1][0] * len(lines[i])
    return '\n'.join(lines)


def _rst_title_index(lines: list[str]) -> int | None:
    """Return the line index of an RST title, or None."""
    for i, line in enumerate(lines):
        if (
            i + 1 < len(lines)
            and lines[i + 1]
            and lines[i + 1][0] in '=-'
            and len(set(lines[i + 1])) == 1
        ):
            return i
    return None


def _build_sphinx_map(packages: list[dict[str, Any]]) -> dict[pathlib.PurePath, str]:
    """Build a mapping from repo-relative file paths to Sphinx doc paths.

    Covers:
    - ``.docs/`` pages (how-to, explanation, tutorials, reference, etc.)
    - Per-library diataxis docs (tutorial, how-to/*, explanation/*)
    - Interface version READMEs (``interfaces/{name}/interface/v{N}/README.md``)
    """
    _DOCS_REL = _DOCS_DIR.relative_to(_REPO_ROOT)
    m: dict[pathlib.PurePath, str] = {}

    # Static .docs/ pages — walk all .md/.rst files (excluding build artifacts).
    _SKIP_DIRS = {'_build', '.sphinx', '.save', 'scripts', 'tests', 'extensions'}
    for path in _DOCS_DIR.rglob('*'):
        if path.suffix not in ('.md', '.rst'):
            continue
        rel = path.relative_to(_DOCS_DIR)
        if rel.parts[0] in _SKIP_DIRS or rel.name.startswith('_'):
            continue
        m[_DOCS_REL / rel] = f'/{rel.with_suffix("")}'

    # Per-library diataxis docs + interface version READMEs.
    for pkg in packages:
        lib_path = pathlib.PurePath(pkg['path'])
        docs: dict[str, list[str]] = pkg.get('docs', {})
        for category, doc_files in docs.items():
            for doc_rel in doc_files:
                stem = pathlib.PurePath(doc_rel).stem
                m[lib_path / doc_rel] = f'/{category}/charmlibs/{lib_path}/{stem}'
        # Interface version READMEs (interfaces/{name}/interface/v{N}/README.md).
        if lib_path.parent.name == 'interfaces':
            interface_dir = _REPO_ROOT / lib_path / 'interface'
            for readme in interface_dir.glob('v[0-9]*/README.md'):
                m[readme.relative_to(_REPO_ROOT)] = f'/reference/interfaces/{lib_path.name}/{readme.parent.name}'

    return m


def _rewrite_links(content: str, source_file: pathlib.Path, sphinx_map: dict[pathlib.PurePath, str]) -> str:
    """Rewrite markdown links: Sphinx paths for known docs, GitHub URLs otherwise."""

    def _replace(m: re.Match[str]) -> str:
        text = m.group(1)
        raw_target = m.group(2)
        # Split off any anchor fragment.
        path_part, sep, raw_fragment = raw_target.partition('#')
        fragment = sep + raw_fragment  # either '' or '#something'
        # Resolve relative to the source file's directory.
        resolved = (source_file.parent / path_part).resolve()
        repo_rel = resolved.relative_to(_REPO_ROOT)  # ValueError if link goes above repo root
        # Look up in the Sphinx map, falling back to GitHub URL.
        url = sphinx_map.get(repo_rel, f'{_REPO_MAIN_URL}/{repo_rel}')
        return f'[{text}]({url}{fragment})'

    _RELATIVE_LINK = (
        r'\[(.+?)\]'       # [link text] -- capture group 1
        r'\('              # (
        r'(?!https?://)'   # not an absolute URL
        r'([^)]+)'         # relative target -- capture group 2
        r'\)'              # )
    )
    return re.sub(_RELATIVE_LINK, _replace, content)


if __name__ == '__main__':
    _main()
