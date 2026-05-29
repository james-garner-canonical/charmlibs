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

"""Sphinx fallback extension for per-library diataxis docs.

The ``diataxis_preprocessor.py`` script (run by ``just docs``) copies library
docs into the Sphinx source tree and generates ``_lib-*.md`` include files.

This extension provides a fallback: if those include files don't exist
(preprocessor didn't run), it writes placeholder versions so that running
``sphinx-build`` alone still produces a working (if incomplete) build.
"""

from __future__ import annotations

import pathlib
import typing

if typing.TYPE_CHECKING:
    import sphinx.application

# Include files that the preprocessor generates and the index pages {include}.
INCLUDE_FILES = {
    'tutorials/_lib-tutorials.md',
    'how-to/_lib-how-to.md',
    'explanation/_lib-explanation.md',
}

FALLBACK_TOCTREE = """\
```{toctree}
:maxdepth: 1

_placeholder
```
"""

FALLBACK_PAGE = '# Library docs placeholder\n\nRun `just docs` to generate library docs.\n'


def setup(app: sphinx.application.Sphinx) -> dict[str, str | bool]:
    """Sphinx extension entrypoint — registers the fallback hook."""
    app.connect('builder-inited', _fallback)
    return {'version': '2.0.0', 'parallel_read_safe': False, 'parallel_write_safe': False}


def _fallback(app: sphinx.application.Sphinx) -> None:
    docs_dir = pathlib.Path(app.confdir)
    for rel_path in INCLUDE_FILES:
        include_file = docs_dir / rel_path
        if not include_file.exists():
            category_dir = include_file.parent
            placeholder_path = category_dir / '_placeholder.md'
            _write_if_needed(path=placeholder_path, content=FALLBACK_PAGE)
            _write_if_needed(path=include_file, content=FALLBACK_TOCTREE)


def _write_if_needed(path: pathlib.Path, content: str) -> None:
    """Write to *path* only if the contents have changed."""
    if not path.exists() or path.read_text() != content:
        path.write_text(content)
