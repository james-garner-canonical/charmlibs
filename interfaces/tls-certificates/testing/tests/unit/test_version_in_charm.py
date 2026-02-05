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

import ops
import ops.testing

import charmlibs.interfaces.tls_certificates as tls_certificates
import charmlibs.interfaces.tls_certificates_testing as tls_certificates_testing


class Charm(ops.CharmBase):
    package_version: str

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        framework.observe(self.on.start, self._on_start)

    def _on_start(self, event: ops.StartEvent):
        self.tls_certificates_version = tls_certificates.__version__


def test_versions_match_in_charm():
    ctx = ops.testing.Context(Charm, meta={"name": "charm"})
    with ctx(ctx.on.start(), ops.testing.State()) as manager:
        manager.run()
        assert tls_certificates_testing.__version__ == manager.charm.tls_certificates_version
