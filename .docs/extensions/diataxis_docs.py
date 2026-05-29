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

"""Copy per-library diataxis docs (tutorials, how-tos, explanations) into the docs site.

Libraries can provide docs in a ``docs/`` directory following this layout::

    <library>/docs/
    ├── tutorial.md
    ├── how-to/
    │   └── <name>.md
    └── explanation/
        └── <name>.md

This extension copies those files into the Sphinx source tree under the matching
diataxis category, following the ``charmlibs/[interfaces/]`` path convention used
by the reference docs. Each file's H1 heading is prefixed with the library name
for identification in toctree listings.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import typing

####################
# Sphinx extension #
####################

if typing.TYPE_CHECKING:
    import sphinx.application


def setup(app: sphinx.application.Sphinx) -> dict[str, str | bool]:
    """Entrypoint for Sphinx extensions, connects generation code to Sphinx event."""
    app.connect('builder-inited', _diataxis_docs)
    return {'version': '1.0.0', 'parallel_read_safe': False, 'parallel_write_safe': False}


def _diataxis_docs(app: sphinx.application.Sphinx) -> None:
    _main(docs_dir=pathlib.Path(app.confdir))


####################
# generation logic #
####################

REPO_MAIN_URL = 'https://github.com/canonical/charmlibs/blob/main'
PLACEHOLDER = '# Temporary TOC placeholder\n'

# Maps source directory name to output directory name.
# tutorial is special-cased (single file, not a directory of files).
CATEGORIES = ('how-to', 'explanation')


def _main(docs_dir: pathlib.Path) -> None:
    """Scan all packages for docs/ directories and copy files into the Sphinx source tree."""
    root = docs_dir.parent
    ls = root / '.scripts' / 'ls.py'
    cmd = [ls, 'packages', '--exclude-examples', '--exclude-placeholders', '--exclude-testing']
    packages = json.loads(subprocess.check_output(cmd, text=True))

    for raw_package in packages:
        lib_docs = root / raw_package / 'docs'
        if not lib_docs.is_dir():
            continue

        lib_name = _lib_name(raw_package)
        is_interface = raw_package.startswith('interfaces/')
        base_url = f'{REPO_MAIN_URL}/{raw_package}/docs'

        # Tutorial: single file -> tutorials/charmlibs/[interfaces/]<lib>.md
        _copy_tutorial(docs_dir, lib_docs, lib_name, is_interface, base_url)

        # How-to and explanation: directory of files
        for category in CATEGORIES:
            _copy_category(docs_dir, lib_docs, lib_name, is_interface, base_url, category)

    # Ensure toctree glob patterns have at least one match to avoid warnings.
    # Same approach as interface_docs.py placeholder pattern.
    _ensure_glob_match(docs_dir / 'tutorials' / 'charmlibs', nested=False)
    _ensure_glob_match(docs_dir / 'tutorials' / 'charmlibs' / 'interfaces', nested=False)
    for category in CATEGORIES:
        _ensure_glob_match(docs_dir / category / 'charmlibs', nested=True)
        _ensure_glob_match(docs_dir / category / 'charmlibs' / 'interfaces', nested=True)


def _copy_tutorial(
    docs_dir: pathlib.Path,
    lib_docs: pathlib.Path,
    lib_name: str,
    is_interface: bool,
    base_url: str,
) -> None:
    """Copy a library's tutorial.md into tutorials/charmlibs/[interfaces/]<lib>.md."""
    for ext in ('.md', '.rst'):
        source = lib_docs / f'tutorial{ext}'
        if source.exists():
            break
    else:
        return

    content = source.read_text()
    content = _prefix_h1(content, lib_name, ext)
    content = _rewrite_relative_links(content, f'{base_url}')

    out_dir = docs_dir / 'tutorials' / 'charmlibs'
    if is_interface:
        out_dir = out_dir / 'interfaces'
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_if_needed(path=out_dir / f'{lib_name}{ext}', content=content)


def _copy_category(
    docs_dir: pathlib.Path,
    lib_docs: pathlib.Path,
    lib_name: str,
    is_interface: bool,
    base_url: str,
    category: str,
) -> None:
    """Copy a library's how-to/ or explanation/ docs into the matching site category."""
    source_dir = lib_docs / category
    if not source_dir.is_dir():
        return

    out_dir = docs_dir / category / 'charmlibs'
    if is_interface:
        out_dir = out_dir / 'interfaces'
    out_dir = out_dir / lib_name
    out_dir.mkdir(parents=True, exist_ok=True)

    for source in sorted(source_dir.iterdir()):
        if source.suffix not in ('.md', '.rst'):
            continue
        content = source.read_text()
        content = _prefix_h1(content, lib_name, source.suffix)
        content = _rewrite_relative_links(content, f'{base_url}/{category}')
        _write_if_needed(path=out_dir / source.name, content=content)


def _lib_name(raw_package: str) -> str:
    """Extract the library name from a package path like 'interfaces/tls-certificates'."""
    return pathlib.PurePosixPath(raw_package).name


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
        if i + 1 < len(lines) and lines[i + 1] and lines[i + 1][0] in '=-' and len(set(lines[i + 1])) == 1:
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


def _ensure_glob_match(directory: pathlib.Path, *, nested: bool) -> None:
    """Ensure a toctree glob pattern has at least one matching document.

    Writes a placeholder file if no real content exists. Removes it if real
    content does exist. Same approach as ``interface_docs.py``.

    For flat globs (``dir/*``), the placeholder is a file in the directory.
    For nested globs (``dir/*/*``), the placeholder is a file inside a
    subdirectory (to match the two-level pattern).
    """
    directory.mkdir(parents=True, exist_ok=True)
    if nested:
        placeholder = directory / '_placeholder' / '_placeholder.md'
        has_real = any(
            f.suffix in ('.md', '.rst')
            for d in directory.iterdir()
            if d.is_dir() and d.name != '_placeholder'
            for f in d.iterdir()
            if f.is_file()
        )
    else:
        placeholder = directory / '_placeholder.md'
        has_real = any(
            f.suffix in ('.md', '.rst') and f.name != '_placeholder.md'
            for f in directory.iterdir()
            if f.is_file()
        )
    if has_real:
        placeholder.unlink(missing_ok=True)
        if nested and placeholder.parent.exists() and not any(placeholder.parent.iterdir()):
            placeholder.parent.rmdir()
    else:
        placeholder.parent.mkdir(parents=True, exist_ok=True)
        _write_if_needed(path=placeholder, content=PLACEHOLDER)


def _write_if_needed(path: pathlib.Path, content: str) -> None:
    """Write to path only if contents are different."""
    if not path.exists() or path.read_text() != content:
        path.write_text(content)
