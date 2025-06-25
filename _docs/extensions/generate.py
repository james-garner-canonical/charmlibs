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
    from typing import Iterable

    import sphinx.application


def setup(app: sphinx.application.Sphinx) -> dict[str, str | bool]:
    """Entrypoint for Sphinx extensions, connects generation code to Sphinx event."""
    app.connect('builder-inited', _generate)
    return {'version': '1.0.0', 'parallel_read_safe': False, 'parallel_write_safe': False}


def _generate(app: sphinx.application.Sphinx):
    _generate_libs_tables(app.confdir)


####################
# Table generation #
####################


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
_LIBS_TABLE_HEADER = """.. list-table::
   :class: sphinx-datatable
   :widths: 1, 40, 1, 60
   :header-rows: 1

   * -
     - name
     - kind
     - description
"""
_KEY_TABLE_HEADER = """.. list-table::
   :widths: 1, 100
   :header-rows: 1

   * -
     - description
"""


class _CSVRow(typing.TypedDict, total=True):
    name: str
    status: str
    url: str
    docs: str
    src: str
    kind: str
    description: str


class _RelCSVRow(_CSVRow, total=True):
    rel_name: str
    rel_url_charmhub: str
    rel_url_schema: str


class _NonRelCSVRow(_CSVRow, total=True):
    machine: str
    K8s: str


def _generate_libs_tables(docs_dir: str | pathlib.Path) -> None:
    ref_dir = pathlib.Path(docs_dir) / 'reference'
    gen_dir = ref_dir / 'generated'
    gen_dir.mkdir(exist_ok=True)
    # relation libs
    with (ref_dir / 'libs-rel-raw.csv').open() as f:
        rel_entries: list[_RelCSVRow] = list(csv.DictReader(f))  # type: ignore
    rel_table = _get_relation_libs_table(rel_entries)
    _write_if_needed(path=(gen_dir / 'libs-rel-table.rst'), content=rel_table)
    # non-relation libs
    with (ref_dir / 'libs-non-rel-raw.csv').open() as f:
        non_rel_entries: list[_NonRelCSVRow] = list(csv.DictReader(f))  # type: ignore
    non_rel_table = _get_non_relation_libs_table(non_rel_entries)
    _write_if_needed(path=(gen_dir / 'libs-non-rel-table.rst'), content=non_rel_table)
    # status key
    key_table = _get_status_key_table()
    msg = ' Library status is shown in the left column. See tooltips, or click here for a key.'
    content = f'.. dropdown::{msg}\n\n' + '\n'.join('   ' + line for line in key_table.split('\n'))
    _write_if_needed(path=(gen_dir / 'status-key-table.rst'), content=content)


def _write_if_needed(path: pathlib.Path, content: str) -> None:
    to_write = _FILE_HEADER + content
    if not path.exists() or path.read_text() != to_write:
        path.write_text(to_write)


##########
# tables #
##########


def _get_relation_libs_table(entries: list[_RelCSVRow]) -> str:
    def key(row: tuple[str, ...]) -> tuple[str, ...]:
        status, _name, _kind, desc = row
        return status, desc

    rows = [(_status(e), _name(e), _kind(e), _rel_description(e)) for e in entries]
    return _LIBS_TABLE_HEADER + _rows_to_rst(sorted(rows, key=key))


def _get_non_relation_libs_table(entries: list[_NonRelCSVRow]) -> str:
    def key(row: tuple[str, ...]) -> tuple[str, ...]:
        status, _name, kind, desc = row
        return status, kind, desc

    rows = [(_status(e), _name(e), _kind(e), _non_rel_description(e)) for e in entries]
    return _LIBS_TABLE_HEADER + _rows_to_rst(sorted(rows, key=key))


def _get_status_key_table() -> str:
    rows = [
        (_status({'status': s}), _STATUS_TOOLTIPS[s])  # type: ignore
        for s in _STATUS_SORTKEYS
        if s in _EMOJIS
    ]
    rows.append(('', 'None of the above.'))
    return _KEY_TABLE_HEADER + _rows_to_rst(rows)


##########
# fields #
##########


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


def _relation(entry: _RelCSVRow) -> str:
    if not (name := entry['rel_name']):
        return ''
    if not (main_url := entry['rel_url_charmhub']):
        return name
    main_link = _rst_link(name, main_url)
    if not (schema_url := entry['rel_url_schema']):
        return main_link
    schema_link = _rst_link('schema', schema_url)
    return f'{main_link} ({schema_link})'


def _rel_description(entry: _RelCSVRow) -> str:
    sortkeys = [
        entry['rel_name'].ljust(64, 'z'),
        str(_STATUS_SORTKEYS[entry['status']]),
        entry['name'],
        str(_KIND_SORTKEYS[entry['kind']]),
    ]
    firstline = _relation(entry)
    return _description(entry, sortkeys=sortkeys, firstline=firstline)


def _non_rel_description(entry: _NonRelCSVRow) -> str:
    substrates = ('machine', 'K8s')
    sortkeys = [
        *('0' if entry[s] else '1' for s in substrates),
        str(_STATUS_SORTKEYS[entry['status']]),
        entry['name'],
        str(_KIND_SORTKEYS[entry['kind']]),
    ]
    firstline = ' '.join(_EMOJIS.get(s, '') + s for s in substrates if entry[s])
    return _description(entry, sortkeys=sortkeys, firstline=firstline)


def _description(entry: _CSVRow, sortkeys: Iterable[str], firstline: str) -> str:
    prefix = _hidden_text(''.join(sortkeys))
    chunks = [x for x in (firstline, entry['description']) if x]
    if not chunks:
        return prefix
    description = '\n'.join(chunks).replace('\n', '\n       | ')
    return f'{prefix}       | {description}'


#######
# rst #
#######


def _rows_to_rst(rows: Iterable[tuple[str, ...]]) -> str:
    lines: list[str] = []
    for row in rows:
        first, *rest = (f' {cell}' if cell and not cell.startswith('\n') else cell for cell in row)
        lines.append(f'   * -{first}\n')
        lines.extend(f'     -{line}\n' for line in rest)
    return ''.join(lines)


def _rst_link(name: str, url: str) -> str:
    return f'`{name.strip()} <{url.strip()}>`__'


def _hidden_text(msg: object) -> str:
    return f"""
       .. raw:: html

          <span style="display:none;" class="hidden-sortkey-text">{msg}</span>

"""
