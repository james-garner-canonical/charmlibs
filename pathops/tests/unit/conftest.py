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

from __future__ import annotations

import ops
import pytest


@pytest.fixture(scope='session')
def container() -> ops.Container:
    return _make_container('test1')


@pytest.fixture(scope='session')
def another_container() -> ops.Container:
    return _make_container('test2')


def _make_container(name: str) -> ops.Container:
    class dummy_backend:  # noqa: N801 (CapWords convention)
        class _juju_context:  # noqa: N801 (CapWords convention)
            version = '9000'

    return ops.Container(
        name=name,
        backend=dummy_backend,  # pyright: ignore[reportArgumentType]
        pebble_client=object(),  # pyright: ignore[reportArgumentType]
    )
