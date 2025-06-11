"""Generate reference/non-relation-libs-table.rst from reference/non-relation-libs-raw.csv"""

from __future__ import annotations

import csv
import pathlib
import typing


_EMOJIS = {
    'recommended': '✅',
    'legacy': '🪦',
    'PyPI': '🐍',
    'Charmhub': '✨',
    'machine': '🖥️',
    'K8s': '☸️',
    'docs': '📚',
    'src': '⌨️',
}


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
   :widths: 1, 40, 10, 15, 35
   :header-rows: 1

   * -
     - name
     - type
     - substrate
     - description
"""]
    for entry in entries:
        items = [
            _EMOJIS.get(entry['status'], ''),
            _rst_link(entry['name'], entry['url']) + _links_str(entry),
            _EMOJIS.get(entry['type'], '') + entry['type'],
            ' '.join(_EMOJIS.get(k, '') + k for k in ('machine', 'K8s') if entry[k]),
            entry['description'],
        ]
        first, *rest = (f' {item}\n' if item else '\n' for item in items)
        chunks.append(f'   * -{first}')
        chunks.extend(f'     -{line}' for line in rest)
    pathlib.Path('reference/non-relation-libs-table.rst').write_text(''.join(chunks))


def _rst_link(name: str, url: str) -> str:
    return f'`{name} <{url}>`__'


def _links_str(entry: _CSVRow) -> str:
    urls = {f'{_EMOJIS.get(k, "")}{k}': entry[k] for k in ('docs', 'src')}
    links = [_rst_link(k, v) for k, v in urls.items() if v]
    return f' ({", ".join(links)})' if links else ''


if __name__ == '__main__':
   _generate_non_relation_libs_table()
