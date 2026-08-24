# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for the testing library from a requirer charm that manages its own private key.

These charms behave differently enough from the library-managed ones to be worth pinning
down: the library deletes any managed key secret, and signs requests with the charm's key.
That means `private_key_secret` is useless to them, and the fixture's certificates only
match if the charm is made to use `DEFAULT_PRIVATE_KEY`.
"""

import ops
import ops.testing
import pytest

import charmlibs.interfaces.tls_certificates_testing as tls_certificates_testing
import requirer_charm_manual


def _relation():
    return tls_certificates_testing.relation_for_requirer(
        endpoint="certificates", certificate_requests=requirer_charm_manual.REQUESTS
    )


def test_the_charms_key_differs_from_the_testing_default():
    """Premise of this whole module: if these ever coincided, the tests below would be vacuous."""
    assert requirer_charm_manual.PRIVATE_KEY != tls_certificates_testing.DEFAULT_PRIVATE_KEY


def test_manual_requirer_deletes_the_managed_key_secret():
    """A charm-supplied key causes the library to remove the secret it would otherwise manage.

    This is why `private_key_secret` must not be used with these charms.
    """
    ctx = ops.testing.Context(
        requirer_charm_manual.ManualRequirerCharm, meta=requirer_charm_manual.META
    )
    relation = _relation()
    secret = tls_certificates_testing.private_key_secret("certificates")
    state_in = ops.testing.State(relations=[relation], secrets=[secret])
    state_out = ctx.run(ctx.on.relation_changed(relation), state_in)
    assert secret.label not in {s.label for s in state_out.secrets}


def test_manual_requirer_signs_requests_with_its_own_key():
    """The charm's key wins, so the requests no longer match the fixture's."""
    ctx = ops.testing.Context(
        requirer_charm_manual.ManualRequirerCharm, meta=requirer_charm_manual.META
    )
    relation = _relation()
    state_in = ops.testing.State(relations=[relation])
    with ctx(ctx.on.relation_changed(relation), state_in) as manager:
        manager.run()
        csrs = manager.charm.certificates.get_csrs_from_requirer_relation_data()
    assert csrs
    for csr in csrs:
        assert csr.certificate_signing_request.matches_private_key(
            requirer_charm_manual.PRIVATE_KEY
        )
        assert not csr.certificate_signing_request.matches_private_key(
            tls_certificates_testing.DEFAULT_PRIVATE_KEY
        )


def test_manual_requirer_gets_no_certs_when_keys_disagree():
    """The fixture's certificates were issued for DEFAULT_PRIVATE_KEY, so they don't match."""
    ctx = ops.testing.Context(
        requirer_charm_manual.ManualRequirerCharm, meta=requirer_charm_manual.META
    )
    state_in = ops.testing.State(relations=[_relation()])
    with ctx(ctx.on.update_status(), state_in) as manager:
        state_out = manager.run()
    assert isinstance(state_out.unit_status, ops.BlockedStatus)
    assert manager.charm.certs is None


def test_manual_requirer_gets_certs_when_made_to_use_the_default_key(
    monkeypatch: pytest.MonkeyPatch,
):
    """Point the charm at DEFAULT_PRIVATE_KEY and the fixture's certificates match.

    A real charm-managed charm would instead be given the key through whatever seam it
    already uses -- Juju config, a user-supplied secret -- rather than by patching.
    """
    monkeypatch.setattr(
        requirer_charm_manual, "PRIVATE_KEY", tls_certificates_testing.DEFAULT_PRIVATE_KEY
    )
    ctx = ops.testing.Context(
        requirer_charm_manual.ManualRequirerCharm, meta=requirer_charm_manual.META
    )
    state_in = ops.testing.State(relations=[_relation()])
    with ctx(ctx.on.update_status(), state_in) as manager:
        state_out = manager.run()
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)
    assert manager.charm.certs is not None
    assert {c.common_name for c in manager.charm.certs} == {
        r.common_name for r in requirer_charm_manual.REQUESTS
    }
