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

import ops.testing

import provider_charm
from charmlibs.interfaces import tls_certificates as tls_certificates
from charmlibs.interfaces import tls_certificates_testing as tls_certificates_testing


def test_provider_no_relation():
    """Test provider charm without any relation - should be ready."""
    ctx = ops.testing.Context(provider_charm.ProviderCharm, meta=provider_charm.META)
    with ctx(ctx.on.update_status(), ops.testing.State()) as manager:
        manager.run()
    assert manager.charm.requests is None


def test_provider_relation_empty():
    """Test provider charm when the relation is empty - should be ready."""
    ctx = ops.testing.Context(provider_charm.ProviderCharm, meta=provider_charm.META)
    relation = ops.testing.Relation("certificates", interface="tls-certificates")
    state = ops.testing.State(relations=[relation])
    with ctx(ctx.on.update_status(), state) as manager:
        manager.run()
    assert manager.charm.requests is None


def test_provider_relation_has_request():
    """Test provider charm receiving a certificate request from a requirer.

    Uses the testing library to populate the relation with a certificate request.
    """
    ctx = ops.testing.Context(provider_charm.ProviderCharm, meta=provider_charm.META)
    requests = [
        tls_certificates.CertificateRequestAttributes(common_name="example.com"),
        tls_certificates.CertificateRequestAttributes(common_name="eggsample.com"),
    ]
    relation = tls_certificates_testing.relation_for_provider(
        endpoint="certificates", certificate_requests=requests
    )
    state_in = ops.testing.State(relations=[relation])
    with ctx(ctx.on.update_status(), state_in) as manager:
        manager.run()
    assert manager.charm.requests is not None
    assert {r.common_name for r in manager.charm.requests} == {r.common_name for r in requests}


def test_provider_relation_unanswered():
    """response=False: requests are present, and this charm hasn't answered any of them.

    The outstanding-request accessors read the provider's own relation data, which the
    library gates on leadership, so the test runs as leader.
    """
    ctx = ops.testing.Context(provider_charm.ProviderCharm, meta=provider_charm.META)
    requests = [
        tls_certificates.CertificateRequestAttributes(common_name="example.com"),
        tls_certificates.CertificateRequestAttributes(common_name="eggsample.com"),
    ]
    relation = tls_certificates_testing.relation_for_provider(
        endpoint="certificates", certificate_requests=requests, response=False
    )
    state_in = ops.testing.State(leader=True, relations=[relation])
    with ctx(ctx.on.update_status(), state_in) as manager:
        manager.run()
        outstanding = manager.charm.certificates.get_outstanding_certificate_requests()
    # the requirer's requests reached the charm ...
    assert manager.charm.requests is not None
    assert {r.common_name for r in manager.charm.requests} == {r.common_name for r in requests}
    # ... and every one of them is still waiting for a certificate
    assert {r.certificate_signing_request.common_name for r in outstanding} == {
        r.common_name for r in requests
    }


def test_provider_relation_answered_has_no_outstanding_requests():
    """The response=True default models this charm having already answered everything.

    Companion to test_provider_relation_unanswered: same requests, opposite outcome, so
    the outstanding-requests assertion there can't be passing vacuously.
    """
    ctx = ops.testing.Context(provider_charm.ProviderCharm, meta=provider_charm.META)
    relation = tls_certificates_testing.relation_for_provider(endpoint="certificates")
    state_in = ops.testing.State(leader=True, relations=[relation])
    with ctx(ctx.on.update_status(), state_in) as manager:
        manager.run()
        outstanding = manager.charm.certificates.get_outstanding_certificate_requests()
    assert manager.charm.requests is not None
    assert not outstanding
