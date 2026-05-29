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

"""Per-library diataxis docs: preprocessor logic and Sphinx fallback extension.

The preprocessor (called from ``just docs``) copies library docs into the Sphinx
source tree and generates include files with explicit toctree entries. The Sphinx
extension provides a fallback: if the include files don't exist (preprocessor
didn't run), it writes placeholder versions so ``sphinx-build`` alone still works.

Libraries can provide docs in a ``docs/`` directory::

    <library>/docs/
    ├── tutorial.md
    ├── how-to/
    │   └── <name>.md
    └── explanation/
        └── <name>.md
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import typing

####################
# Sphinx extension #
####################

if typing.TYPE_CHECKING:
    import sphinx.application

# Include files that the preprocessor generates and the index pages {include}.
INCLUDE_FILES = {
    'tutorials/_lib-tutorials.md',
    'how-to/_lib-howtos.md',
    'explanation/_lib-explanations.md',
}

FALLBACK_TOCTREE = """\
```{toctree}
:maxdepth: 1

_placeholder
```
"""

FALLBACK_PAGE = '# Library docs placeholder\n\nRun `just docs` to generate library docs.\n'


def setup(app: sphinx.application.Sphinx) -> dict[str, str | bool]:
    """Sphinx extension entrypoint — fallback only.

    Writes placeholder include files if the preprocessor hasn't run, so that
    ``sphinx-build`` alone still produces a working (if incomplete) build.
    """
    app.connect('builder-inited', _fallback)
    return {'version': '2.0.0', 'parallel_read_safe': False, 'parallel_write_safe': False}


def _fallback(app: sphinx.application.Sphinx) -> None:
    docs_dir = pathlib.Path(app.confdir)
    for rel_path in INCLUDE_FILES:
        include_file = docs_dir / rel_path
        if not include_file.exists():
            # Write a placeholder page + toctree that references it.
            category_dir = include_file.parent
            placeholder_path = category_dir / '_placeholder.md'
            _write_if_needed(path=placeholder_path, content=FALLBACK_PAGE)
            _write_if_needed(path=include_file, content=FALLBACK_TOCTREE)


######################
# preprocessor logic #
######################

REPO_MAIN_URL = 'https://github.com/canonical/charmlibs/blob/main'
CATEGORIES = ('how-to', 'explanation')

TOCTREE_HEADER = """\
```{toctree}
:maxdepth: 1

"""
TOCTREE_FOOTER = '```\n'


def main(docs_dir: pathlib.Path) -> None:
    """Entry point for the preprocessor. Called from ``just docs``."""
    docs_dir = docs_dir.resolve()
    root = docs_dir.parent
    ls = root / '.scripts' / 'ls.py'
    cmd = [sys.executable, str(ls), 'packages', '--exclude-examples', '--exclude-placeholders', '--exclude-testing']
    packages: list[str] = json.loads(subprocess.check_output(cmd, text=True))

    # Collect toctree entries while copying files.
    tutorial_entries: list[str] = []
    howto_entries: list[str] = []
    explanation_entries: list[str] = []

    for raw_package in packages:
        lib_docs = root / raw_package / 'docs'
        if not lib_docs.is_dir():
            continue

        lib_name = _lib_name(raw_package)
        is_interface = raw_package.startswith('interfaces/')
        base_url = f'{REPO_MAIN_URL}/{raw_package}/docs'

        # Tutorial
        toc = _copy_tutorial(docs_dir, lib_docs, lib_name, is_interface, base_url)
        if toc:
            tutorial_entries.append(toc)

        # How-to and explanation
        for category, entries in (('how-to', howto_entries), ('explanation', explanation_entries)):
            toc_list = _copy_category(docs_dir, lib_docs, lib_name, is_interface, base_url, category)
            entries.extend(toc_list)

    # Write include files (always, even if empty — so the fallback knows not to run).
    _write_include(docs_dir / 'tutorials' / '_lib-tutorials.md', tutorial_entries)
    _write_include(docs_dir / 'how-to' / '_lib-howtos.md', howto_entries)
    _write_include(docs_dir / 'explanation' / '_lib-explanations.md', explanation_entries)


def _copy_tutorial(
    docs_dir: pathlib.Path,
    lib_docs: pathlib.Path,
    lib_name: str,
    is_interface: bool,
    base_url: str,
) -> str | None:
    """Copy a library's tutorial and return its toctree entry, or None."""
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
    out_dir = docs_dir / 'tutorials' / rel_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f'{lib_name}{ext}'
    _write_if_needed(path=out_path, content=content)

    # Toctree entry: "tls-certificates: Getting Started <charmlibs/interfaces/tls-certificates>"
    doc_ref = f'{rel_dir}/{lib_name}'
    return f'{lib_name}: {title} <{doc_ref}>'


def _copy_category(
    docs_dir: pathlib.Path,
    lib_docs: pathlib.Path,
    lib_name: str,
    is_interface: bool,
    base_url: str,
    category: str,
) -> list[str]:
    """Copy a library's how-to or explanation docs. Return toctree entries."""
    source_dir = lib_docs / category
    if not source_dir.is_dir():
        return []

    rel_dir = 'charmlibs/interfaces' if is_interface else 'charmlibs'
    out_dir = docs_dir / category / rel_dir / lib_name
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
    """Write a toctree include file. Empty file if no entries."""
    if entries:
        content = TOCTREE_HEADER + '\n'.join(entries) + '\n' + TOCTREE_FOOTER
    else:
        content = ''
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_if_needed(path=path, content=content)


###########
# helpers #
###########


def _lib_name(raw_package: str) -> str:
    """Extract the library name from a package path like 'interfaces/tls-certificates'."""
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

    For MyST (.md): ``# Title`` -> ``# tls-certificates: Title``
    For RST (.rst): underlined title (first line is title, second is underline).
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
    """Rewrite relative (non-HTTP) markdown links to absolute GitHub URLs.

    Same pattern as ``interface_docs.py``.
    """
    return re.sub(
        r'\[(.+?)\]\((?!https?://)([^)]+)\)',
        lambda m: f'[{m.group(1)}]({base_url}/{m.group(2)})',
        content,
    )


def _write_if_needed(path: pathlib.Path, content: str) -> None:
    """Write to path only if contents are different."""
    if not path.exists() or path.read_text() != content:
        path.write_text(content)
