"""Generate reference/non-relation-libs-table.rst from reference/non-relation-libs-raw.csv"""

from __future__ import annotations

import csv
import pathlib
import typing


_EMOJIS = {
    'recommended': '✅',
    'dep': '↪️',
    '': '',
    'legacy': '🪦',
    'team': '🚫',
    # 'PyPI': '🐍',
    # 'Charmhub': '✨',
    'machine': '🖥️',
    'K8s': '☸️',
    # 'docs': '📚',
    # 'src': '⌨️',
}

_PRIORITIES = {s: i for i, s in enumerate(_EMOJIS)}


class _CSVRow(typing.TypedDict, total=True):
    name: str
    status: str
    url: str
    docs: str
    src: str
    type: str
    machine: str
    K8s: str
    description: str


def _generate_non_relation_libs_table():
    raw = pathlib.Path('reference/non-relation-libs-raw.csv')
    with raw.open() as f:
        entries: list[_CSVRow] = list(csv.DictReader(f))  # type: ignore
    chunks = [f"""..
    This file was automatically generated.
    It should not be manually edited!
    Instead, edit {raw} and then run {pathlib.Path(__file__).name}

.. list-table::
   :class: sphinx-datatable
   :widths: 2, 40, 8, 50
   :header-rows: 1

   * -
     - name
     - type
     - description
"""]
    for entry in entries:
        items = [
            _hidden_text_prefix(_PRIORITIES[entry["status"]]) + _EMOJIS[entry["status"]],
            _rst_link(entry['name'], entry['url']) + _links_str(entry),
            _EMOJIS.get(entry['type'], '') + entry['type'],
            _description(entry),
        ]
        first, *rest = (
            f' {item}' if item and not item.startswith('\n') else item for item in items
        )
        chunks.append(f'   * -{first}\n')
        chunks.extend(f'     -{line}\n' for line in rest)
    pathlib.Path('reference/non-relation-libs-table.rst').write_text(''.join(chunks))


def _hidden_text_prefix(msg: object) -> str:
    return f'\n       .. raw:: html\n\n          <span style="display:none;">{msg}</span>\n\n       | '


def _rst_link(name: str, url: str) -> str:
    return f'`{name} <{url}>`__'


def _links_str(entry: _CSVRow) -> str:
    urls = {f'{_EMOJIS.get(k, "")}{k}': entry[k] for k in ('docs', 'src')}
    links = [_rst_link(k, v) for k, v in urls.items() if v]
    return f' ({", ".join(links)})' if links else ''


def _description(entry: _CSVRow) -> str:
    substrate = ' '.join(_EMOJIS.get(k, '') + k for k in ('machine', 'K8s') if entry[k])
    description = '\n'.join(x for x in (substrate, entry['description']) if x)
    prefix = ('| ' if '\n' in description else '')
    return prefix + description.replace('\n', '\n       | ')


if __name__ == '__main__':
   _generate_non_relation_libs_table()
