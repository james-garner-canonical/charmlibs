# Copyright 2026 Canonical Ltd.
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

"""Testing package for ``charmlibs.interfaces.certificate_transfer``.

Two independent pieces of API. :func:`provider` and :func:`requirer` return a
:class:`CharmData` describing a stand-in charm for the other end of a
``certificate_transfer`` relation, to be deployed alongside the charm under test with
``ops.testing.Juju``; and :func:`mocked` mocks the library's internals for the duration of
a test.

A requirer charm under test is paired with :func:`provider`, and a provider charm with
:func:`requirer` -- the stand-in plays the opposite role.

``certificate_transfer`` is a one-way interface: the provider hands CA certificates to the
requirer, which reads them and answers nothing. The one thing the requirer does say is
which version of the wire format it understands, and it says it first -- so a stand-in
requirer advertises what its arguments say, while a stand-in provider derives the *format*
of its answer from what the charm under test actually advertised, exactly as the real
provider library does.
"""

from ._charm_data import CharmData
from ._mocking import mocked
from ._testing import provider, requirer
from ._version import __version__ as __version__

__all__ = [
    # only the names listed in __all__ are imported when executing:
    # from charmlibs.interfaces.certificate_transfer_testing import *
    'CharmData',
    'mocked',
    'provider',
    'requirer',
]
