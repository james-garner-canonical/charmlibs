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

"""Generate reference/non-relation-libs-table.rst from reference/non-relation-libs-raw.csv."""

from __future__ import annotations

import csv
import pathlib
import typing

####################
# Sphinx extension #
####################

if typing.TYPE_CHECKING:
    from typing import Callable, Iterable

    import sphinx.application
    from typing_extensions import TypeAlias


def setup(app: sphinx.application.Sphinx) -> dict[str, str | bool]:
    """Entrypoint for Sphinx extensions, connects generation code to Sphinx event."""
    app.connect('builder-inited', _generate)
    return {'version': '1.0.0', 'parallel_read_safe': False, 'parallel_write_safe': False}


def _generate(app: sphinx.application.Sphinx):
    _generate_libs_table(app.confdir)


####################################
# Generate non-relation libs table #
####################################

_EMOJIS = {
    # status
    'recommended': '✅',
    'dep': '↪️',
    'experimental': '⚗️',
    'legacy': '🪦',
    'team': '🚫',
    # substrate
    'machine': '🖥️',
    'K8s': '☸️',
}
_STATUS_TOOLTIPS = {
    'recommended': 'Recommended for use in new charms today!',
    'dep': 'Dependency of other libs, unlikely to be required directly.',
    'experimental': 'Experimental, use at your own risk!',
    'legacy': 'Not recommended, there are better alternatives available.',
    'team': 'Team internal lib, may not be stable for external use.',
}
_KIND_SORTKEYS = {'PyPI': 0, 'git': 1, 'Charmhub': 2, '': 3}
_STATUS_SORTKEYS = {'recommended': 0, '': 1, 'dep': 2, 'experimental': 3, 'legacy': 4, 'team': 5}
_FILE_HEADER = """..
    This file was automatically generated.
    It should not be manually edited!
    Instead, edit the corresponding -raw.csv file and then rebuild the docs.

"""
_REL_TABLE_HEADER = """.. list-table::
   :class: sphinx-datatable
   :widths: 1, 20, 20, 1, 40
   :header-rows: 1

   * -
     - relation
     - name
     - kind
     - description
"""
_NON_REL_TABLE_HEADER = """.. list-table::
   :class: sphinx-datatable
   :widths: 1, 40, 1, 60
   :header-rows: 1

   * -
     - name
     - kind
     - description
"""


class _RelCSVRow(typing.TypedDict, total=True):
    rel_name: str
    rel_url: str
    name: str
    status: str
    url: str
    docs: str
    src: str
    kind: str
    description: str


class _NonRelCSVRow(typing.TypedDict, total=True):
    name: str
    status: str
    url: str
    docs: str
    src: str
    kind: str
    machine: str
    K8s: str
    description: str


_CSVRow: TypeAlias = '_RelCSVRow | _NonRelCSVRow'
_TableRow: TypeAlias = 'tuple[str, ...]'


def _generate_libs_table(docs_dir: str | pathlib.Path) -> None:
    ref_dir = pathlib.Path(docs_dir) / 'reference'
    gen_dir = ref_dir / 'generated'
    gen_dir.mkdir(exist_ok=True)
    # relation libs
    with (ref_dir / 'relation-libs-raw.csv').open() as f:
        rel_entries: list[_RelCSVRow] = list(csv.DictReader(f))  # type: ignore
    rel_table = _get_relation_libs_table(rel_entries)
    (gen_dir / 'relation-libs-table.rst').write_text(rel_table)
    # non-relation libs
    with (ref_dir / 'non-relation-libs-raw.csv').open() as f:
        non_rel_entries: list[_NonRelCSVRow] = list(csv.DictReader(f))  # type: ignore
    non_rel_table = _get_non_relation_libs_table(non_rel_entries)
    (gen_dir / 'non-relation-libs-table.rst').write_text(non_rel_table)


def _get_relation_libs_table(entries: list[_RelCSVRow]) -> str:
    def key(row: _TableRow) -> _TableRow:
        status, rel, name, kind, desc = row
        return status, kind, rel, name, desc

    rows = [(_status(e), _relation(e), _name(e), _kind(e), _description(e)) for e in entries]
    rst = _rows_to_rst(rows, key=key)
    return ''.join([_FILE_HEADER, _REL_TABLE_HEADER, rst])


def _get_non_relation_libs_table(entries: list[_NonRelCSVRow]) -> str:
    def key(row: _TableRow) -> _TableRow:
        status, name, kind, desc = row
        return status, kind, desc, name

    rows = [(_status(e), _name(e), _kind(e), _description(e)) for e in entries]
    rst = _rows_to_rst(rows, key=key)
    return ''.join([_FILE_HEADER, _NON_REL_TABLE_HEADER, rst])


def _rows_to_rst(rows: Iterable[_TableRow], key: Callable[[_TableRow], _TableRow]) -> str:
    lines: list[str] = []
    for row in sorted(rows, key=key):
        first, *rest = (f' {cell}' if cell and not cell.startswith('\n') else cell for cell in row)
        lines.append(f'   * -{first}\n')
        lines.extend(f'     -{line}\n' for line in rest)
    return ''.join(lines)


def _status(entry: _CSVRow) -> str:
    status = entry['status']
    prefix = _hidden_text(_STATUS_SORTKEYS[status])
    if status not in _EMOJIS:
        return prefix
    if status not in _STATUS_TOOLTIPS:
        return f'{prefix}       | {_EMOJIS[status]}'
    return f"""{prefix.rstrip()}
          <div class="emoji-div">
            {_EMOJIS[status]}
            <div class="emoji-tooltip">{_STATUS_TOOLTIPS[status]}</div>
          </div>

"""


def _relation(entry: _RelCSVRow) -> str:
    if not (name := entry['rel_name']):
        return '?'
    if not (url := entry['rel_url']):
        return name
    return _rst_link(name, url)


def _name(entry: _CSVRow) -> str:
    main_link = _rst_link(entry['name'], entry['url'])
    extra_links = ', '.join([
        _rst_link(_EMOJIS.get(text, '') + text, url)
        for text in ('docs', 'src')
        if (url := entry[text])
    ])
    if not extra_links:
        return main_link
    return f'{main_link} ({extra_links})'


def _kind(entry: _CSVRow) -> str:
    kind = entry['kind']
    prefix = _hidden_text(_KIND_SORTKEYS[kind])
    kind_str = _EMOJIS.get(kind, '') + kind
    if not kind_str:
        return prefix
    return f'{prefix}       | {kind_str}'


def _description(entry: _CSVRow) -> str:
    substrates = ('machine', 'K8s')
    # prefix
    sortkeys = ''.join([
        *('0' if entry.get(s, '') else '1' for s in substrates),
        str(_STATUS_SORTKEYS[entry['status']]),
        str(_KIND_SORTKEYS[entry['kind']]),
        entry['name'],
    ])
    prefix = _hidden_text(sortkeys)
    # description
    subs = ' '.join(_EMOJIS.get(s, '') + s for s in substrates if entry.get(s, ''))
    desc = entry['description']
    description = '\n'.join(s for s in (subs, desc) if s).replace('\n', '\n       | ')
    if not description:
        return prefix
    return f'{prefix}       | {description}'


def _rst_link(name: str, url: str) -> str:
    return f'`{name.strip()} <{url.strip()}>`__'


def _hidden_text(msg: object) -> str:
    return f"""
       .. raw:: html

          <span style="display:none;">{msg}</span>

"""
