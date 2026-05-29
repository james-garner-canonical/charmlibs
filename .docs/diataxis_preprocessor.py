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

_DOCS_DIR = pathlib.Path(__file__).parent.resolve()
_REPO_ROOT = _DOCS_DIR.parent
_REPO_MAIN_URL = 'https://github.com/canonical/charmlibs/blob/main'
_CATEGORIES = ('how-to', 'explanation')
_TOCTREE_HEADER = """\
```{toctree}
:maxdepth: 1

"""
_TOCTREE_FOOTER = '```\n'


def _main() -> None:
    """Discover packages and copy their docs into the Sphinx source tree."""
    ls = _REPO_ROOT / '.scripts' / 'ls.py'
    cmd = [str(ls), 'packages', '--exclude-examples', '--exclude-placeholders', '--exclude-testing']
    packages: list[str] = json.loads(subprocess.check_output(cmd, text=True))

    tutorial_entries: list[str] = []
    howto_entries: list[str] = []
    explanation_entries: list[str] = []

    for raw_package in packages:
        lib_docs = _REPO_ROOT / raw_package / 'docs'
        if not lib_docs.is_dir():
            continue

        lib_name = _lib_name(raw_package)
        is_interface = raw_package.startswith('interfaces/')
        base_url = f'{_REPO_MAIN_URL}/{raw_package}/docs'

        entry = _copy_tutorial(lib_docs, lib_name, is_interface, base_url)
        if entry:
            tutorial_entries.append(entry)

        for category, entries in (('how-to', howto_entries), ('explanation', explanation_entries)):
            entries.extend(_copy_category(lib_docs, lib_name, is_interface, base_url, category))

    # Write include files (always, even if empty — so the fallback extension knows not to run).
    _write_include(_DOCS_DIR / 'tutorials' / '_lib-tutorials.md', tutorial_entries)
    _write_include(_DOCS_DIR / 'how-to' / '_lib-howtos.md', howto_entries)
    _write_include(_DOCS_DIR / 'explanation' / '_lib-explanations.md', explanation_entries)


def _copy_tutorial(
    lib_docs: pathlib.Path,
    lib_name: str,
    is_interface: bool,
    base_url: str,
) -> str | None:
    """Copy a library's tutorial and return its toctree entry, or ``None``."""
    for ext in ('.md', '.rst'):
        source = lib_docs / f'tutorial{ext}'
        if source.exists():
            break
    else:
        return None

    content = source.read_text()
    title = _extract_h1(content, ext)
    content = _prefix_h1(content, lib_name, ext)
    content = _rewrite_relative_links(content, base_url)

    rel_dir = 'charmlibs/interfaces' if is_interface else 'charmlibs'
    out_dir = _DOCS_DIR / 'tutorials' / rel_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_if_needed(path=out_dir / f'{lib_name}{ext}', content=content)

    doc_ref = f'{rel_dir}/{lib_name}'
    return f'{lib_name}: {title} <{doc_ref}>'


def _copy_category(
    lib_docs: pathlib.Path,
    lib_name: str,
    is_interface: bool,
    base_url: str,
    category: str,
) -> list[str]:
    """Copy a library's how-to or explanation docs and return toctree entries."""
    source_dir = lib_docs / category
    if not source_dir.is_dir():
        return []

    rel_dir = 'charmlibs/interfaces' if is_interface else 'charmlibs'
    out_dir = _DOCS_DIR / category / rel_dir / lib_name
    out_dir.mkdir(parents=True, exist_ok=True)

    entries: list[str] = []
    for source in sorted(source_dir.iterdir()):
        if source.suffix not in ('.md', '.rst'):
            continue
        content = source.read_text()
        title = _extract_h1(content, source.suffix)
        content = _prefix_h1(content, lib_name, source.suffix)
        content = _rewrite_relative_links(content, f'{base_url}/{category}')
        _write_if_needed(path=out_dir / source.name, content=content)

        doc_ref = f'{rel_dir}/{lib_name}/{source.stem}'
        entries.append(f'{lib_name}: {title} <{doc_ref}>')

    return entries


def _write_include(path: pathlib.Path, entries: list[str]) -> None:
    """Write a toctree include file, or an empty file if there are no entries."""
    if entries:
        content = _TOCTREE_HEADER + '\n'.join(entries) + '\n' + _TOCTREE_FOOTER
    else:
        content = ''
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_if_needed(path=path, content=content)


def _lib_name(raw_package: str) -> str:
    """Extract the library name from a package path like ``interfaces/tls-certificates``."""
    return pathlib.PurePosixPath(raw_package).name


def _extract_h1(content: str, ext: str) -> str:
    """Extract the first H1 heading text from content."""
    if ext == '.md':
        match = re.search(r'^# (.+)$', content, re.MULTILINE)
        return match.group(1).strip() if match else 'Untitled'
    # RST
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if (
            i + 1 < len(lines)
            and lines[i + 1]
            and lines[i + 1][0] in '=-'
            and len(set(lines[i + 1])) == 1
        ):
            return line.strip()
    return 'Untitled'


def _prefix_h1(content: str, lib_name: str, ext: str) -> str:
    """Prepend the library name to the first H1 heading.

    For MyST (.md): ``# Title`` -> ``# lib: Title``
    For RST (.rst): underlined title with adjusted underline length.
    """
    if ext == '.md':
        return re.sub(r'^(# )', rf'\1{lib_name}: ', content, count=1, flags=re.MULTILINE)
    # RST: title is the first non-empty line, followed by an underline of = or -
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if (
            i + 1 < len(lines)
            and lines[i + 1]
            and lines[i + 1][0] in '=-'
            and len(set(lines[i + 1])) == 1
        ):
            new_title = f'{lib_name}: {line}'
            lines[i] = new_title
            lines[i + 1] = lines[i + 1][0] * len(new_title)
            break
    return '\n'.join(lines)


def _rewrite_relative_links(content: str, base_url: str) -> str:
    """Rewrite relative (non-HTTP) markdown links to absolute GitHub URLs."""
    return re.sub(
        r'\[(.+?)\]\((?!https?://)([^)]+)\)',
        lambda m: f'[{m.group(1)}]({base_url}/{m.group(2)})',
        content,
    )


def _write_if_needed(path: pathlib.Path, content: str) -> None:
    """Write to *path* only if the contents have changed."""
    if not path.exists() or path.read_text() != content:
        path.write_text(content)


if __name__ == '__main__':
    _main()
