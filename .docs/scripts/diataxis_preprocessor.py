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

_DOCS_DIR = pathlib.Path(__file__).parent.parent.resolve()
_REPO_ROOT = _DOCS_DIR.parent
_REPO_MAIN_URL = 'https://github.com/canonical/charmlibs/blob/main'
# Mapping from ls.py docs keys to Sphinx output directory names.
_CATEGORIES: dict[str, str] = {'tutorial': 'tutorials', 'how-to': 'how-to', 'explanation': 'explanation'}
_TOCTREE_HEADER = """\
```{toctree}
:maxdepth: 1

"""
_TOCTREE_FOOTER = '```\n'


def _main() -> None:
    """Discover packages and copy their docs into the Sphinx source tree."""
    ls = _REPO_ROOT / '.scripts' / 'ls.py'
    cmd = [
        str(ls),
        'packages',
        '--exclude-examples',
        '--exclude-placeholders',
        '--exclude-testing',
        '--output', 'path',
        '--output', 'docs',
    ]
    packages: list[dict[str, object]] = json.loads(subprocess.check_output(cmd, text=True))

    # Build the mapping of repo-relative paths to Sphinx doc paths.
    sphinx_map = _build_sphinx_map(packages)

    all_entries: dict[str, list[str]] = {cat_dir: [] for cat_dir in _CATEGORIES.values()}

    for pkg in packages:
        raw_package = str(pkg['path'])
        docs: dict[str, list[str]] = pkg.get('docs', {})  # type: ignore[assignment]
        lib_name = _lib_name(raw_package)
        is_interface = raw_package.startswith('interfaces/')

        for docs_key, cat_dir in _CATEGORIES.items():
            sources = [_REPO_ROOT / raw_package / f for f in docs.get(docs_key, [])]
            all_entries[cat_dir].extend(
                _copy_category(sources, lib_name, is_interface, cat_dir, sphinx_map)
            )

    # Write include files (always, even if empty — so the fallback extension knows not to run).
    _write_include(_DOCS_DIR / 'tutorials' / '_lib-tutorials.md', all_entries['tutorials'])
    _write_include(_DOCS_DIR / 'how-to' / '_lib-howtos.md', all_entries['how-to'])
    _write_include(_DOCS_DIR / 'explanation' / '_lib-explanations.md', all_entries['explanation'])


def _copy_category(
    sources: list[pathlib.Path],
    lib_name: str,
    is_interface: bool,
    category: str,
    sphinx_map: dict[str, str],
) -> list[str]:
    """Copy a library's how-to or explanation docs and return toctree entries."""
    rel_dir = 'charmlibs/interfaces' if is_interface else 'charmlibs'
    out_dir = _DOCS_DIR / category / rel_dir / lib_name

    entries: list[str] = []
    for source in sources:
        out_dir.mkdir(parents=True, exist_ok=True)
        content = source.read_text()
        title = _extract_h1(content, source.suffix)
        content = _prefix_h1(content, lib_name, source.suffix)
        content = _rewrite_links(content, source, sphinx_map)
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


def _normalize(name: str) -> str:
    """Normalize a package name to the form used in reference doc paths.

    Matches the PyPI name normalization used by ``package_docs.py``.
    """
    return re.sub(r'[-_.]+', '-', name).lower()


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


def _build_sphinx_map(packages: list[dict[str, object]]) -> dict[str, str]:
    """Build a mapping from repo-relative file paths to Sphinx doc paths.

    Covers:
    - ``.docs/`` pages (how-to, explanation, tutorials, reference, etc.)
    - Per-library diataxis docs (tutorial, how-to/*, explanation/*)
    - Interface version READMEs (``interfaces/{name}/interface/v{N}/README.md``)
    - Package READMEs (``{pkg}/README.md``)
    """
    m: dict[str, str] = {}

    # Static .docs/ pages — walk all .md/.rst files (excluding build artifacts).
    for path in _DOCS_DIR.rglob('*'):
        if path.suffix not in ('.md', '.rst'):
            continue
        rel = path.relative_to(_DOCS_DIR)
        parts = rel.parts
        # Skip build artifacts, generated dirs, and include files.
        if parts[0] in ('_build', '.sphinx', '.save', 'scripts', 'tests', 'extensions'):
            continue
        if rel.name.startswith('_'):
            continue
        repo_rel = f'.docs/{rel}'
        sphinx_doc = str(rel.with_suffix(''))
        m[repo_rel] = f'/{sphinx_doc}'

    # Per-library diataxis docs and package READMEs.
    for pkg in packages:
        raw_package = str(pkg['path'])
        docs: dict[str, list[str]] = pkg.get('docs', {})  # type: ignore[assignment]
        lib_name = _lib_name(raw_package)
        is_interface = raw_package.startswith('interfaces/')
        rel_dir = 'charmlibs/interfaces' if is_interface else 'charmlibs'

        # Package README → reference page.
        norm_name = _normalize(lib_name)
        if is_interface:
            m[f'{raw_package}/README.md'] = f'/reference/charmlibs/interfaces/{norm_name}'
        else:
            m[f'{raw_package}/README.md'] = f'/reference/charmlibs/{norm_name}'

        # Diataxis docs (tutorial, how-to, explanation).
        for docs_key, cat_dir in _CATEGORIES.items():
            for doc_rel in docs.get(docs_key, []):
                stem = pathlib.PurePosixPath(doc_rel).stem
                m[f'{raw_package}/{doc_rel}'] = f'/{cat_dir}/{rel_dir}/{lib_name}/{stem}'

    # Interface version READMEs (interfaces/{name}/interface/v{N}/README.md).
    for pkg in packages:
        raw_package = str(pkg['path'])
        if not raw_package.startswith('interfaces/'):
            continue
        interface_name = _lib_name(raw_package)
        interface_dir = _REPO_ROOT / raw_package / 'interface'
        if not interface_dir.is_dir():
            continue
        for v_dir in interface_dir.glob('v[0-9]*'):
            readme = v_dir / 'README.md'
            if readme.exists():
                repo_rel = str(readme.relative_to(_REPO_ROOT))
                m[repo_rel] = f'/reference/interfaces/{interface_name}/{v_dir.name}'

    return m


def _rewrite_links(content: str, source_file: pathlib.Path, sphinx_map: dict[str, str]) -> str:
    """Rewrite markdown links: Sphinx paths for known docs, GitHub URLs otherwise."""
    source_dir = source_file.parent

    def _replace(m: re.Match[str]) -> str:
        text = m.group(1)
        raw_target = m.group(2)

        # Split off any anchor fragment.
        if '#' in raw_target:
            path_part, fragment = raw_target.rsplit('#', 1)
            fragment = f'#{fragment}'
        else:
            path_part = raw_target
            fragment = ''

        # Resolve relative to the source file's directory.
        resolved = (source_dir / path_part).resolve()
        try:
            repo_rel = str(resolved.relative_to(_REPO_ROOT))
        except ValueError:
            raise ValueError(
                f'{source_file}: link target {raw_target!r} resolves outside the repo'
            ) from None

        # Look up in the Sphinx map.
        if repo_rel in sphinx_map:
            return f'[{text}]({sphinx_map[repo_rel]}{fragment})'

        # Fall back to GitHub URL.
        return f'[{text}]({_REPO_MAIN_URL}/{repo_rel}{fragment})'

    return re.sub(
        r'\[(.+?)\]\((?!https?://)([^)]+)\)',
        _replace,
        content,
    )


def _write_if_needed(path: pathlib.Path, content: str) -> None:
    """Write to *path* only if the contents have changed."""
    if not path.exists() or path.read_text() != content:
        path.write_text(content)


if __name__ == '__main__':
    _main()
