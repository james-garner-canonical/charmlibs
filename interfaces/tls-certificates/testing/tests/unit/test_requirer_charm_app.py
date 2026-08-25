# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for the testing library from a Mode.APP requirer charm's perspective.

In APP mode the certificate belongs to the application: requests live in the app databag,
the managed key secret is app-owned, and the library only lets the leader touch either.
Non-leaders see no key and no certificates -- by design, not by accident -- so both sides
of that split need pinning.
"""

import ops
import ops.testing

import charmlibs.interfaces.tls_certificates as tls_certificates
import charmlibs.interfaces.tls_certificates_testing as tls_certificates_testing
import requirer_charm_app


def _state(*, leader: bool) -> ops.testing.State:
    relation = tls_certificates_testing.relation_for_requirer(
        endpoint="certificates",
        mode=tls_certificates.Mode.APP,
        certificate_requests=requirer_charm_app.REQUESTS,
    )
    secret = tls_certificates_testing.private_key_secret(
        "certificates", mode=tls_certificates.Mode.APP
    )
    return ops.testing.State(leader=leader, relations=[relation], secrets=[secret])


def test_app_requirer_leader_gets_certs():
    """The leader sees the seeded app key and the certificates issued against it."""
    ctx = ops.testing.Context(requirer_charm_app.AppRequirerCharm, meta=requirer_charm_app.META)
    with ctx(ctx.on.update_status(), _state(leader=True)) as manager:
        state_out = manager.run()
        assigned, private_key = manager.charm.certificates.get_assigned_certificates()
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)
    # the leader reads the key back from the app-owned secret
    assert private_key == tls_certificates_testing.DEFAULT_PRIVATE_KEY
    assert {c.certificate.common_name for c in assigned} == {
        r.common_name for r in requirer_charm_app.REQUESTS
    }


def test_app_requirer_non_leader_gets_no_certs():
    """Only the leader can access the private key (and app CSRs) in APP mode.

    The state is identical to the leader test's -- key seeded, certificates issued --
    so the blocked status can only come from the leadership gate.
    """
    ctx = ops.testing.Context(requirer_charm_app.AppRequirerCharm, meta=requirer_charm_app.META)
    with ctx(ctx.on.update_status(), _state(leader=False)) as manager:
        state_out = manager.run()
        assigned, private_key = manager.charm.certificates.get_assigned_certificates()
        csrs = manager.charm.certificates.get_csrs_from_requirer_relation_data()
    assert isinstance(state_out.unit_status, ops.BlockedStatus)
    # the library refuses the non-leader the key and the app requests
    assert private_key is None
    assert not csrs
    assert not assigned
    assert manager.charm.certs is None
