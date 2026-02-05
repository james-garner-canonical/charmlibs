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

"""Tests for the TLS Certificates testing library from a provider charm perspective."""

from typing import Any

import ops
import ops.testing

import charmlibs.interfaces.tls_certificates as tls_certificates
import charmlibs.interfaces.tls_certificates_testing as tls_certificates_testing


class ProviderCharm(ops.CharmBase):
    """A minimal provider charm for testing the TLS Certificates interface."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.certificates = tls_certificates.TLSCertificatesProvidesV4(self, "certificates")
        framework.observe(self.on.start, self._on_start)
        framework.observe(self.on.certificates_relation_joined, self._on_relation_joined)
        framework.observe(self.on.certificates_relation_changed, self._on_relation_changed)

    def _on_start(self, event: ops.StartEvent) -> None:
        """Handle the start event by setting status to ready."""
        self.unit.status = ops.ActiveStatus("ready")

    def _on_relation_joined(self, event: ops.RelationJoinedEvent) -> None:
        """Handle relation joined event."""
        pass

    def _on_relation_changed(self, event: ops.RelationChangedEvent) -> None:
        """Handle relation changed event with certificate requests."""
        # For this test, just acknowledge the request by providing dummy certificates
        certificate_requests = self.certificates.get_certificate_requests(event.relation)
        for csr in certificate_requests:
            # Use simple strings as certificate values for testing
            self.certificates.set_relation_certificate(
                relation=event.relation,
                certificate_signing_request=csr,
                certificate="cert1",
                ca="ca1",
                chain=["chain1"],
            )
        # Set status after processing requests
        self.unit.status = ops.ActiveStatus("ready")


def test_provider_no_relation():
    """Test provider charm without any relation - should be ready."""
    ctx = ops.testing.Context(
        ProviderCharm,
        meta={
            "name": "provider",
            "provides": {"certificates": {"interface": "tls-certificates"}},
        },
    )
    with ctx(ctx.on.start(), ops.testing.State()) as manager:
        manager.run()
        assert manager.charm.unit.status == ops.ActiveStatus("ready")


def test_provider_relation_joined():
    """Test provider charm when a requirer joins the relation."""
    ctx = ops.testing.Context(
        ProviderCharm,
        meta={
            "name": "provider",
            "provides": {"certificates": {"interface": "tls-certificates"}},
        },
    )
    relation = ops.testing.Relation("certificates", interface="tls-certificates", id=0)
    state = ops.testing.State(relations=[relation])

    # Trigger relation-joined event
    state_out = ctx.run(ctx.on.relation_joined(relation), state)
    # Just verify the charm can process the event without errors


def test_provider_relation_changed_with_request():
    """Test provider charm receiving a certificate request from a requirer.

    Uses the testing library to populate the relation with a certificate request.
    """
    ctx = ops.testing.Context(
        ProviderCharm,
        meta={
            "name": "provider",
            "provides": {"certificates": {"interface": "tls-certificates"}},
        },
    )
    # Use the testing library to create a relation with a requirer request
    relation = tls_certificates_testing.for_local_provider(
        endpoint="certificates",
        certificate_requests=[
            tls_certificates.CertificateRequestAttributes(common_name="example.com")
        ],
    )
    state = ops.testing.State(relations=[relation])

    # Trigger relation-changed event
    state_out = ctx.run(ctx.on.relation_changed(relation), state)
    # Verify the charm processed the certificate request and is ready
    assert state_out.unit_status == ops.ActiveStatus("ready")
