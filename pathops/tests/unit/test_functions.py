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

"""Tests that don't use a real Pebble to test helper functions."""

from __future__ import annotations

import pathlib
import stat
import typing

import ops
import pytest
from ops import pebble

import utils
from charmlibs.pathops import ContainerPath, LocalPath, _constants, ensure_bytes, ensure_text
from charmlibs.pathops._functions import _get_fileinfo

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any


@pytest.mark.parametrize(
    ('mock', 'error'),
    (
        (utils.raise_connection_error, pebble.ConnectionError),
        (utils.raise_unknown_api_error, pebble.APIError),
    ),
)
def test_get_fileinfo_reraises_unhandled_pebble_errors(
    monkeypatch: pytest.MonkeyPatch,
    container: ops.Container,
    mock: Callable[[Any], None],
    error: type[Exception],
):
    monkeypatch.setattr(container, 'list_files', mock)
    with pytest.raises(error):
        _get_fileinfo(ContainerPath('/', container=container))


@pytest.mark.parametrize('path_type', [str, pathlib.Path, LocalPath])
@pytest.mark.parametrize(
    ('initial', 'result', 'expected_arg', 'changed'),
    (
        (None, 'hello\r\n', None, True),
        (None, '', None, True),
        (b'', '', '', False),
        (b'', 'x', '', True),
        ('héllo\r\n'.encode(), 'héllo\r\n', 'héllo\r\n', False),
        (b'hello', '', 'hello', True),
    ),
)
def test_ensure_text(
    tmp_path: pathlib.Path,
    path_type: type[str] | type[pathlib.Path],
    initial: bytes | None,
    result: str,
    expected_arg: str | None,
    changed: bool,
):
    path = tmp_path / 'parent' / 'path'
    if initial is not None:
        path.parent.mkdir()
        path.write_bytes(initial)
        path.chmod(_constants.DEFAULT_WRITE_MODE)
    calls: list[str | None] = []

    def transform(existing: str | None) -> str:
        calls.append(existing)
        return result

    assert ensure_text(path_type(path), transform) == changed
    assert calls == [expected_arg]
    assert path.read_bytes() == result.encode()
    assert stat.S_IMODE(path.stat().st_mode) == _constants.DEFAULT_WRITE_MODE


@pytest.mark.parametrize('path_type', [str, pathlib.Path, LocalPath])
@pytest.mark.parametrize(
    ('initial', 'result', 'changed'),
    (
        (None, b'\xff\x00', True),
        (None, b'', True),
        (b'', b'', False),
        (b'\xff\x00', b'\xff\x00', False),
        (b'\xff\x00', b'\xff', True),
    ),
)
def test_ensure_bytes(
    tmp_path: pathlib.Path,
    path_type: type[str] | type[pathlib.Path],
    initial: bytes | None,
    result: bytes,
    changed: bool,
):
    path = tmp_path / 'parent' / 'path'
    if initial is not None:
        path.parent.mkdir()
        path.write_bytes(initial)
        path.chmod(_constants.DEFAULT_WRITE_MODE)
    calls: list[bytes | None] = []

    def transform(existing: bytes | None) -> bytes:
        calls.append(existing)
        return result

    assert ensure_bytes(path_type(path), transform) == changed
    assert calls == [initial]
    assert path.read_bytes() == result


@pytest.mark.parametrize('func', [ensure_text, ensure_bytes])
def test_ensure_enforces_mode_when_contents_unchanged(
    tmp_path: pathlib.Path, func: Callable[..., bool]
):
    path = tmp_path / 'path'
    path.write_bytes(b'x')
    path.chmod(0o600)
    assert func(path, lambda existing: existing, mode=0o640)  # pyright: ignore[reportUnknownLambdaType]
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert path.read_bytes() == b'x'
    assert not func(path, lambda existing: existing, mode=0o640)  # pyright: ignore[reportUnknownLambdaType]


@pytest.mark.parametrize(
    ('func', 'bad'),
    [(ensure_text, None), (ensure_text, b'x'), (ensure_bytes, None), (ensure_bytes, 'x')],
)
@pytest.mark.parametrize('exists', [True, False])
def test_ensure_rejects_wrong_return_type(
    tmp_path: pathlib.Path, func: Callable[..., bool], bad: object, exists: bool
):
    path = tmp_path / 'path'
    if exists:
        path.write_bytes(b'x')
        path.chmod(0o600)
    with pytest.raises(TypeError):
        func(path, lambda _: bad, mode=0o644)  # pyright: ignore[reportUnknownLambdaType]
    if exists:
        assert path.read_bytes() == b'x'
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    else:
        assert not path.exists()


class _TransformError(Exception):
    pass


def _raise(_: object) -> typing.NoReturn:
    raise _TransformError()


@pytest.mark.parametrize('func', [ensure_text, ensure_bytes])
@pytest.mark.parametrize('exists', [True, False])
def test_ensure_propagates_transform_errors_without_changes(
    tmp_path: pathlib.Path, func: Callable[..., bool], exists: bool
):
    path = tmp_path / 'parent' / 'path'
    if exists:
        path.parent.mkdir()
        path.write_bytes(b'x')
        path.chmod(0o600)
    with pytest.raises(_TransformError):
        func(path, _raise, mode=0o644)
    if exists:
        assert path.read_bytes() == b'x'
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    else:
        assert not path.parent.exists()


def test_ensure_text_propagates_decode_errors_without_changes(tmp_path: pathlib.Path):
    path = tmp_path / 'path'
    path.write_bytes(b'\xff')
    path.chmod(0o600)
    calls: list[str | None] = []

    def transform(existing: str | None) -> str:
        calls.append(existing)
        return ''

    with pytest.raises(UnicodeDecodeError):
        ensure_text(path, transform, mode=0o644)
    assert not calls
    assert path.read_bytes() == b'\xff'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
