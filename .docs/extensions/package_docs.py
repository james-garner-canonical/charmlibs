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

"""Generate automodule files and table of contents for packages."""

from __future__ import annotations

import pathlib
import typing

####################
# Sphinx extension #
####################

if typing.TYPE_CHECKING:
    import sphinx.application


def setup(app: sphinx.application.Sphinx) -> dict[str, str | bool]:
    """Entrypoint for Sphinx extensions, connects generation code to Sphinx event."""
    app.connect('builder-inited', _package_docs)
    return {'version': '1.0.0', 'parallel_read_safe': False, 'parallel_write_safe': False}


def _package_docs(app: sphinx.application.Sphinx):
    _generate_files(app.confdir)


####################
# generation logic #
####################

AUTOMODULE_TEMPLATE = """
{package}
{underline}

.. automodule:: {package}
""".strip()

INDEX_TEMPLATE = """
# Charmlibs

```{toctree}
:maxdepth: 1

{packages}
```
""".strip()


def _generate_files(docs_dir: str | pathlib.Path) -> None:
    reference_dir = pathlib.Path(docs_dir) / 'reference' / 'charmlibs'
    packages = sorted(
        path
        for path in pathlib.Path().glob(r'[a-z]*')
        if path.is_dir() and path.name != 'interfaces'
    )
    for package in packages:
        file_contents = AUTOMODULE_TEMPLATE.format(
            package=package.name, underline='=' * len(package.name)
        )
        _write_if_needed(path=(reference_dir / f'{package}.rst'), contents=file_contents)
    index_contents = INDEX_TEMPLATE.format(packages='\n'.join(packages))
    _write_if_needed(path=(reference_dir / 'index.md'), contents=index_contents)


def _write_if_needed(path: pathlib.Path, content: str) -> None:
    """Write to path only if contents are different.

    This allows sphinx-build to skip rebuilding pages that depend on the output of this extension
    if the output hasn't actually changed.
    """
    to_write = _FILE_HEADER + content
    if not path.exists() or path.read_text() != to_write:
        path.write_text(to_write)
