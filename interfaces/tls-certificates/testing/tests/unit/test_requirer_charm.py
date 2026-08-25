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

"""Tests for the testing library from a library-managed requirer charm's perspective.

See test_requirer_charm_manual.py for a charm that manages its own private key.
"""

import ops
import ops.testing

import charmlibs.interfaces.tls_certificates as tls_certificates
import charmlibs.interfaces.tls_certificates_testing as tls_certificates_testing
import requirer_charm


def test_requirer_no_relation():
    """Test requirer charm without any relation - should be blocked."""
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    with ctx(ctx.on.update_status(), ops.testing.State()) as manager:
        state_out = manager.run()
    assert isinstance(state_out.unit_status, ops.BlockedStatus)
    assert manager.charm.certs is None


def test_requirer_relation_empty():
    """Test requirer charm when the relation is joined."""
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    relation = ops.testing.Relation("certificates", interface="tls-certificates")
    state_in = ops.testing.State(relations=[relation])
    with ctx(ctx.on.update_status(), state_in) as manager:
        state_out = manager.run()
    assert isinstance(state_out.unit_status, ops.BlockedStatus)
    assert manager.charm.certs is None


def test_requirer_relation_has_certs():
    """Test requirer charm receiving certificates from a provider.

    The charm lets the library manage its private key, so the test seeds the key secret
    the library would have created. No charm internals are patched.
    """
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    relation = tls_certificates_testing.relation_for_requirer(
        endpoint="certificates", certificate_requests=requirer_charm.REQUESTS
    )
    secret = tls_certificates_testing.private_key_secret("certificates")
    state_in = ops.testing.State(relations=[relation], secrets=[secret])
    with ctx(ctx.on.update_status(), state_in) as manager:
        state_out = manager.run()
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)
    assert manager.charm.certs is not None
    assert {c.common_name for c in manager.charm.certs} == {
        r.common_name for r in requirer_charm.REQUESTS
    }


def test_requirer_relation_has_certs_on_relation_changed():
    """The seeded key also works on an event that runs the library's reconcile logic.

    Without the seeded secret the library would generate its own key here and overwrite
    the fixture's CSRs, silently resolving no certificates.
    """
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    relation = tls_certificates_testing.relation_for_requirer(
        endpoint="certificates", certificate_requests=requirer_charm.REQUESTS
    )
    secret = tls_certificates_testing.private_key_secret("certificates")
    state_in = ops.testing.State(relations=[relation], secrets=[secret])
    with ctx(ctx.on.relation_changed(relation), state_in) as manager:
        manager.run()
        assigned, private_key = manager.charm.certificates.get_assigned_certificates()
    assert private_key == tls_certificates_testing.DEFAULT_PRIVATE_KEY
    assert {c.certificate.common_name for c in assigned} == {
        r.common_name for r in requirer_charm.REQUESTS
    }


def test_requirer_relation_unanswered():
    """response=False: the charm has asked, but the provider hasn't answered yet.

    This is the most common real intermediate state: the requirer's requests are in the
    databag, and the provider hasn't issued anything. The charm should report blocked
    because the provider hasn't answered -- not because it failed to ask.
    """
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    relation = tls_certificates_testing.relation_for_requirer(
        endpoint="certificates",
        certificate_requests=requirer_charm.REQUESTS,
        response=False,
    )
    secret = tls_certificates_testing.private_key_secret("certificates")
    state_in = ops.testing.State(relations=[relation], secrets=[secret])
    with ctx(ctx.on.update_status(), state_in) as manager:
        state_out = manager.run()
        csrs = manager.charm.certificates.get_csrs_from_requirer_relation_data()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    # the charm's requests made it to the relation ...
    assert {csr.certificate_signing_request.common_name for csr in csrs} == {
        r.common_name for r in requirer_charm.REQUESTS
    }
    # ... but nothing has been issued for them
    assert not assigned
    assert isinstance(state_out.unit_status, ops.BlockedStatus)
    assert manager.charm.certs is None


def test_certificate_available_fires_on_every_reconcile():
    """The library emits certificate_available per certificate on *every* reconcile.

    The event is level-triggered: it fires even when the stored secret already holds
    exactly the certificate on the relation, so charms must reconcile against installed
    state rather than treat it as a change signal. Pin that here as documented behaviour
    rather than an accident.
    """
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    relation = tls_certificates_testing.relation_for_requirer(
        endpoint="certificates", certificate_requests=requirer_charm.REQUESTS
    )
    secret = tls_certificates_testing.private_key_secret("certificates")
    state = ops.testing.State(relations=[relation], secrets=[secret])
    reconciles = 3
    for _ in range(reconciles):
        relation = state.get_relations("certificates")[0]
        state = ctx.run(ctx.on.relation_changed(relation), state)
    available = [
        e for e in ctx.emitted_events if isinstance(e, tls_certificates.CertificateAvailableEvent)
    ]
    # one event per certificate per reconcile, despite nothing changing between runs
    assert len(available) == reconciles * len(requirer_charm.REQUESTS)
    assert {e.certificate.common_name for e in available} == {
        r.common_name for r in requirer_charm.REQUESTS
    }


def test_fixture_state_is_stable_across_reconciles():
    """Repeated reconciles must not rewrite the databag or trip certificate renewal.

    The fixture's certificates start at 0% of their validity, well short of the library's
    renewal threshold. If that ever regressed (say, by issuing nearly-expired
    certificates), the library would withdraw the fixture's CSRs and replace them on the
    first reconcile, invalidating every test built on the fixture being inert.
    """
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    relation = tls_certificates_testing.relation_for_requirer(
        endpoint="certificates", certificate_requests=requirer_charm.REQUESTS
    )
    # This test is *about* the databag staying byte-identical, so reading the raw
    # relation data is the point -- charm tests should never do this.
    original_csrs = relation.local_unit_data["certificate_signing_requests"]
    secret = tls_certificates_testing.private_key_secret("certificates")
    state = ops.testing.State(relations=[relation], secrets=[secret])
    for _ in range(3):
        state = ctx.run(ctx.on.relation_changed(state.get_relations("certificates")[0]), state)
        relation_out = state.get_relations("certificates")[0]
        assert relation_out.local_unit_data["certificate_signing_requests"] == original_csrs


def test_requirer_without_key_secret_gets_no_certs():
    """Regression guard: this is the failure mode private_key_secret exists to prevent."""
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    relation = tls_certificates_testing.relation_for_requirer(
        endpoint="certificates", certificate_requests=requirer_charm.REQUESTS
    )
    state_in = ops.testing.State(relations=[relation])  # no key secret
    with ctx(ctx.on.update_status(), state_in) as manager:
        state_out = manager.run()
    assert isinstance(state_out.unit_status, ops.BlockedStatus)
    assert manager.charm.certs is None
