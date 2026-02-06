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

"""Type checking statements for LocalPath and ContainerPath."""

import pathlib

from charmlibs.pathops import ContainerPath, LocalPath, PathProtocol


def _requires_path(p: pathlib.Path) -> None: ...


def _requires_protocol(p: PathProtocol) -> None: ...


def typecheck_container_path_implements_protocol(path: ContainerPath) -> None:
    _requires_protocol(path)


def typecheck_local_path_implemnents_protocol(path: LocalPath) -> None:
    _requires_protocol(path)


def typecheck_local_path_is_pathlib_path(path: LocalPath) -> None:
    _requires_path(path)


def typecheck_container_path_is_compatible_with_protocol() -> None:
    class SubClass(ContainerPath, PathProtocol):  # pyright: ignore[reportUnusedClass]
        pass


def typecheck_local_path_is_compatible_with_protocol() -> None:
    class SubClass(LocalPath, PathProtocol):  # pyright: ignore[reportUnusedClass]
        pass
