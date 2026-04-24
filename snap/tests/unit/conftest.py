# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
from __future__ import annotations

import json
import pathlib
from types import SimpleNamespace
from typing import Any

import pytest

FIXTURES_DIR = pathlib.Path(__file__).parent / 'fixtures'


def load_fixture(name: str) -> Any:
    """Load a fixture file. Returns the full API envelope dict, or a list for logs_lxd.json."""
    return json.loads((FIXTURES_DIR / name).read_text())


def result_of(name: str) -> Any:
    """Return the 'result' field from a fixture — what _client.get/put returns for sync ops."""
    data = load_fixture(name)
    if isinstance(data, list):
        return data  # logs_lxd.json is already a list
    return data['result']


@pytest.fixture
def mock_client(mocker):
    """Patch _client.get, .post, and .put for use in _snapd_*.py tests."""
    return SimpleNamespace(
        get=mocker.patch('charmlibs.snap._client.get'),
        post=mocker.patch('charmlibs.snap._client.post'),
        put=mocker.patch('charmlibs.snap._client.put'),
    )
