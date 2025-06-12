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

_EMOJIS = {
    # statuses
    'recommended': '✅',
    'dep': '↪️',
    'legacy': '🪦',
    'team': '🚫',
    # kinds
    # 'PyPI': '🐍',
    # 'git': '🔧',
    # 'Charmhub': '✨',
    # substrates
    'machine': '🖥️',
    'K8s': '☸️',
    # other
    # 'docs': '📚',
    # 'src': '⌨️',
}
_STATUS_DESCRIPTIONS = {
    'recommended': 'Recommended for use in new charms today!',
    'dep': 'Dependency of other libs, unlikely to be needed directly.',
    'legacy': 'There are better alternatives available.',
    'team': 'Team internal lib, may not be stable for external use.',
}
_KIND_PRIORITIES = {'PyPI': 0, 'git': 1, 'Charmhub': 2}
_STATUS_PRIORITIES = {s: i for i, s in enumerate(('recommended', 'dep', '', 'legacy', 'team'))}
_SUBSTRATE_PRIORITIES = {'K8s': 0, 'machine': 1, '': 2}


class _CSVRow(typing.TypedDict, total=True):
    name: str
    status: str
    url: str
    docs: str
    src: str
    kind: str
    machine: str
    K8s: str
    description: str


def _generate_non_relation_libs_table():
    raw = pathlib.Path('reference/non-relation-libs-raw.csv')
    with raw.open() as f:
        entries: list[_CSVRow] = list(csv.DictReader(f))  # type: ignore
    chunks = [
        f"""..
    This file was automatically generated.
    It should not be manually edited!
    Instead, edit {raw} and then run {pathlib.Path(__file__).name}

.. list-table::
   :class: sphinx-datatable
   :widths: 1, 40, 1, 60
   :header-rows: 1

   * -
     - name
     - kind
     - description
""",
    ]
    rows = [(_status(entry), _name(entry), _kind(entry), _description(entry)) for entry in entries]
    for row in sorted(rows, key=lambda r: (r[0], r[2], r[3], r[1])):  # sort: status, kind, desc
        first, *rest = (f' {cell}' if cell and not cell.startswith('\n') else cell for cell in row)
        chunks.append(f'   * -{first}\n')
        chunks.extend(f'     -{line}\n' for line in rest)
    pathlib.Path('reference/non-relation-libs-table.rst').write_text(''.join(chunks))


def _status(entry: _CSVRow) -> str:
    status = entry['status']
    prefix = _hidden_text(_STATUS_PRIORITIES[status])
    if status not in _EMOJIS:
        return prefix
    if status not in _STATUS_DESCRIPTIONS:
        return f'{prefix}       | {_EMOJIS[status]}'
    return (
        prefix.rstrip()
        + '\n          '
        + f'<div class="emoji-div">{_EMOJIS[status]}'
        + f'<div class="emoji-tooltip">{_STATUS_DESCRIPTIONS[status]}</div>'
        + '</div>'
        + '\n\n'
    )


def _name(entry: _CSVRow, one_line: bool = True) -> str:
    name = _rst_link(entry['name'], entry['url'])
    assert name
    urls = {f'{_EMOJIS.get(k, "")}{k}': entry[k] for k in ('docs', 'src')}
    links = [_rst_link(k, v) for k, v in urls.items() if v]
    if not links:
        return name
    links_str = ', '.join(links)
    if one_line:
        return f'{name} ({links_str})'
    return f'| {name}\n       | ({links_str})'


def _kind(entry: _CSVRow) -> str:
    kind = entry['kind']
    prefix = _hidden_text(_KIND_PRIORITIES[kind])
    kind_str = _EMOJIS.get(kind, '') + kind
    if not kind_str:
        return prefix
    return f'{prefix}       | {kind_str}'


def _description(entry: _CSVRow) -> str:
    substrates = ('machine', 'K8s')
    priorities = ''.join(str(_SUBSTRATE_PRIORITIES[s if entry[s] else '']) for s in substrates)
    prefix = _hidden_text(priorities)
    substrate_line = ' '.join(_EMOJIS.get(s, '') + s for s in substrates if entry[s])
    description = '\n'.join(x for x in (substrate_line, entry['description']) if x)
    if not description:
        return prefix
    description_str = description.replace('\n', '\n       | ')
    return f'{prefix}       | {description_str}'


def _rst_link(name: str, url: str) -> str:
    return f'`{name} <{url}>`__'


def _hidden_text(msg: object) -> str:
    return f"""
       .. raw:: html

          <span style="display:none;">{msg}</span>

"""


if __name__ == '__main__':
    _generate_non_relation_libs_table()
