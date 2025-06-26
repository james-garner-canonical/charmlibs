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

# ruff: noqa: D103 (function docstrings)
# ruff: noqa: S314 (unsecure xml parsing)
# ruff: noqa: S405 (unsecure xml parsing)

"""Unit tests for the 'generate' local Sphinx extension."""

from __future__ import annotations

import html
import xml.etree.ElementTree as ElementTree

import generate
import pytest
from docutils import core


def rst_to_html(rst: str) -> str:
    return core.publish_parts(rst, writer_name='html')['html_body']  # type: ignore


def test_status_key_table():
    rst = generate._get_status_key_table()
    html_content = rst_to_html(rst)
    print(html_content)
    table = ElementTree.fromstring(html.unescape(html_content)).find('.//table')
    assert table is not None


@pytest.mark.parametrize('rows', ([('r1c1', 'r1c2'), ('r2c1', 'r2c2')],))
def test_rst_rows(rows: list[tuple[str, ...]]):
    rst = generate._rst_rows(rows)
    html_content = rst_to_html(f'.. list-table::\n\n{rst}')
    table = ElementTree.fromstring(html_content).find('.//table')
    assert table is not None
    table_rows = table.findall('.//tr')
    assert len(table_rows) == len(rows)
    for i, row in enumerate(table_rows):
        table_cells = row.findall('.//td')
        assert len(table_cells) == len(rows[i])
        for table_cell, cell in zip(table_cells, rows[i]):
            assert table_cell.text == cell


@pytest.mark.parametrize(('text', 'url'), [('foo', 'bar')])
def test_html_link(text: str, url: str):
    html_content = generate._html_link(text, url)
    a = ElementTree.fromstring(html_content)
    assert a is not None
    assert a.attrib['href'] == url
    assert a.text == text


@pytest.mark.parametrize('msg', ['foo', 1])
def test_html_hidden_div(msg: str):
    html_content = generate._html_hidden_span(msg)
    span = ElementTree.fromstring(html_content)
    assert span is not None
    assert 'display:none;' in span.attrib['style']
    assert span.text == str(msg)
