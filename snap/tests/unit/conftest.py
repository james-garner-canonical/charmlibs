# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast
from unittest import mock

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from unittest.mock import MagicMock

FIXTURES_DIR = pathlib.Path(__file__).parent / 'fixtures'


class Mocker:
    """Minimal stand-in for :class:`pytest_mock.MockerFixture`.

    Only :meth:`patch` is supported. Started patches are stopped automatically
    when the ``mocker`` fixture tears down.
    """

    def __init__(self) -> None:
        self._patchers: list[Any] = []

    def patch(self, target: str, /, *args: Any, **kwargs: Any) -> MagicMock:
        patcher = cast('Any', mock.patch(target, *args, **kwargs))
        mocked: MagicMock = patcher.start()
        self._patchers.append(patcher)
        return mocked

    def stopall(self) -> None:
        for patcher in reversed(self._patchers):
            patcher.stop()


@pytest.fixture
def mocker() -> Iterator[Mocker]:
    m = Mocker()
    yield m
    m.stopall()


@dataclass
class MockClient:
    get: MagicMock
    get_logs: MagicMock
    post: MagicMock
    put: MagicMock


@pytest.fixture
def mock_client(mocker: Mocker) -> MockClient:
    """Patch _client.get, .get_logs, .post, and .put for use in _snapd_*.py tests."""
    return MockClient(
        get=mocker.patch('charmlibs.snap._client.get'),
        get_logs=mocker.patch('charmlibs.snap._client.get_logs'),
        post=mocker.patch('charmlibs.snap._client.post'),
        put=mocker.patch('charmlibs.snap._client.put'),
    )


def load_fixture(name: str) -> Any:
    """Load a fixture file. Returns the full API envelope dict, or a list for logs_lxd.json."""
    return json.loads((FIXTURES_DIR / name).read_text())


def result_of(name: str) -> Any:
    """Return the 'result' field from a fixture — what _client.get/put returns for sync ops."""
    data = load_fixture(name)
    if isinstance(data, list):
        return data  # pyright: ignore[reportUnknownVariableType]
    return data['result']
