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

"""Include interface reference docs in docs site."""

from __future__ import annotations

import json
import pathlib
import subprocess
import typing

####################
# Sphinx extension #
####################

if typing.TYPE_CHECKING:
    import sphinx.application


def setup(app: sphinx.application.Sphinx) -> dict[str, str | bool]:
    """Entrypoint for Sphinx extensions, connects generation code to Sphinx event."""
    app.connect('builder-inited', _interface_docs)
    return {'version': '1.0.0', 'parallel_read_safe': False, 'parallel_write_safe': False}


def _interface_docs(app: sphinx.application.Sphinx) -> None:
    _main(docs_dir=pathlib.Path(app.confdir))


####################
# generation logic #
####################

RST_TEMPLATE = """
{interface}
{underline}
""".strip()


def _main(docs_dir: pathlib.Path) -> None:
    """Write automodule file for package and placeholders rst files for all other packages."""
    root = docs_dir.parent
    target_dir = docs_dir / 'reference' / 'interfaces'
    target_dir.mkdir(parents=True, exist_ok=True)
    cmd = [root / '.scripts/ls.py', 'interfaces', '--exclude-examples', '--exclude-placeholders']
    interfaces = json.loads(subprocess.check_output(cmd, text=True))
    for path_str in interfaces:
        _, _, interface = path_str.rpartition('/')
        content = RST_TEMPLATE.format(
            interface=interface,
            underline='=' * len(interface),
        )
        _write_if_needed(path=target_dir / f'{interface}.rst', content=content)


def _write_if_needed(path: pathlib.Path, content: str) -> None:
    """Write to path only if contents are different.

    This allows sphinx-build to skip rebuilding pages that depend on the output of this extension
    if the output hasn't actually changed.
    """
    if not path.exists() or path.read_text() != content:
        path.write_text(content)
