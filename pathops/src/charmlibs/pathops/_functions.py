# Copyright 2024 Canonical Ltd.
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

"""Public helper functions exported by this package."""

from __future__ import annotations

import pathlib
import typing

from . import _constants, _fileinfo
from ._container_path import ContainerPath
from ._local_path import LocalPath

if typing.TYPE_CHECKING:
    import os
    from collections.abc import Callable
    from typing import BinaryIO, TextIO

    from ops import pebble
    from typing_extensions import TypeIs

    from ._types import PathProtocol


def ensure_contents(
    path: str | os.PathLike[str] | PathProtocol,
    source: bytes | str | BinaryIO | TextIO,
    *,
    mode: int = _constants.DEFAULT_WRITE_MODE,
    user: str | None = None,
    group: str | None = None,
) -> bool:
    """Ensure ``source`` can be read from ``path``. Return True if any changes were made.

    Ensure that ``path`` exists, contains ``source``, has the correct permissions (``mode``),
    and has the correct file ownership (``user`` and ``group``).

    Args:
        path: A local or remote filesystem path.
        source: The desired contents in ``str`` or ``bytes`` form, or an object with a ``.read()``
            method which returns a ``str`` or ``bytes`` object.
        mode: The desired file permissions.
        user: The desired file owner, or ``None`` to not change the owner.
        group: The desired group, or ``None`` to not change the group.

    Returns:
        ``True`` if any changes were made, including permissions or ownership, otherwise ``False``.

    Raises:
        LookupError: if the user or group is unknown.
        NotADirectoryError: if the parent exists as a non-directory file.
        PermissionError: if the user does not have permissions for the operation.
        :class:`PebbleConnectionError`: if the remote Pebble client cannot be reached.
    """
    if _is_str_pathlike(path):
        path = LocalPath(path)
    source = _as_bytes(source)
    try:
        info = _get_fileinfo(path)
    except FileNotFoundError:
        pass  # file doesn't exist, so writing is required
    else:  # check if metadata and contents already match
        if _metadata_matches(info, mode=mode, user=user, group=group) and (
            path.read_bytes() == source
        ):
            return False  # everything matches, so writing is not required
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(source, mode=mode, user=user, group=group)
    return True


def ensure_text(
    path: str | os.PathLike[str] | PathProtocol,
    transform: Callable[[str | None], str],
    *,
    mode: int = _constants.DEFAULT_WRITE_MODE,
    user: str | None = None,
    group: str | None = None,
) -> bool:
    r"""Ensure ``path`` contains the text from ``transform``. Return True if any changes were made.

    The existing contents of ``path`` are read once and decoded as UTF-8, then passed to
    ``transform``, which is called exactly once. If the file doesn't exist, ``transform``
    receives ``None``. An empty file supplies ``''``. ``transform`` must return the desired
    complete contents of the file as a ``str``, which is encoded as UTF-8 and written if it
    differs from the file's current contents. A missing file is always created, even if the
    result is empty.

    Newlines are handled as by :meth:`PathProtocol.read_text` and
    :meth:`PathProtocol.write_text`: ``transform`` receives the text with all newlines
    (``'\r\n'``, ``'\r'``, and ``'\n'``) translated to ``'\n'``, and the text it returns is
    written as is, so the file always ends up containing exactly the returned text. This means
    that if the file uses ``'\r\n'`` or ``'\r'`` line endings, the first call rewrites it with
    ``'\n'`` line endings (and returns ``True``), even if ``transform`` returns its input
    unchanged.

    Like :func:`ensure_contents`, missing parent directories are created, and the file's
    permissions (``mode``) and ownership (``user`` and ``group``) are enforced even when the
    contents are unchanged.

    ``transform`` is responsible for any editing policy (for example, appending a line only if
    it's not already present), and for its own idempotence. The read and the write are separate
    operations, so concurrent modification of the file between them is not detected.

    If reading, decoding, or ``transform`` raises an exception, it's propagated without the file
    being written or its metadata being changed.

    Args:
        path: A local or remote filesystem path.
        transform: Called with the existing text, or ``None`` if the file doesn't exist.
            Returns the desired text.
        mode: The desired file permissions.
        user: The desired file owner, or ``None`` to not change the owner.
        group: The desired group, or ``None`` to not change the group.

    Returns:
        ``True`` if any changes were made, including file creation, permissions, or ownership,
        otherwise ``False``.

    Raises:
        TypeError: if ``transform`` doesn't return a ``str``.
        UnicodeDecodeError: if the existing contents aren't valid UTF-8.
        IsADirectoryError: if ``path`` is a directory.
        LookupError: if the user or group is unknown.
        NotADirectoryError: if the parent exists as a non-directory file.
        PermissionError: if the user does not have permissions for the operation.
        :class:`PebbleConnectionError`: if the remote Pebble client cannot be reached.
    """
    if _is_str_pathlike(path):
        path = LocalPath(path)
    try:
        existing_bytes = path.read_bytes()  # Avoid Path.read_text's locale-dependent encoding.
    except FileNotFoundError:
        existing_bytes = None
    if existing_bytes is None:
        transformed_bytes = _encode_text(transform(None))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(transformed_bytes, mode=mode, user=user, group=group)
        return True
    existing_text = existing_bytes.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
    transformed_bytes = _encode_text(transform(existing_text))
    if transformed_bytes == existing_bytes:
        info = _get_fileinfo(path)
        if _metadata_matches(info, mode=mode, user=user, group=group):
            return False  # everything matches, so writing is not required
    path.write_bytes(transformed_bytes, mode=mode, user=user, group=group)
    return True


def _encode_text(text: str) -> bytes:
    if not isinstance(text, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError(f'transform must return str, not {type(text).__name__}')
    return text.encode('utf-8')


def _metadata_matches(
    info: pebble.FileInfo, *, mode: int, user: str | None, group: str | None
) -> bool:
    return (
        (info.permissions == mode)
        and (user is None or info.user == user)
        and (group is None or info.group == group)
    )


def _is_str_pathlike(obj: object) -> TypeIs[str | os.PathLike[str]]:
    return isinstance(obj, str) or hasattr(obj, '__fspath__')


def _get_fileinfo(
    path: str | os.PathLike[str] | PathProtocol, follow_symlinks: bool = True
) -> pebble.FileInfo:
    if isinstance(path, ContainerPath):
        return _fileinfo.from_container_path(path, follow_symlinks=follow_symlinks)
    assert _is_str_pathlike(path)
    return _fileinfo.from_pathlib_path(pathlib.Path(path), follow_symlinks=follow_symlinks)


def _as_bytes(source: bytes | str | BinaryIO | TextIO) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, str):
        return source.encode()
    return _as_bytes(source.read())
