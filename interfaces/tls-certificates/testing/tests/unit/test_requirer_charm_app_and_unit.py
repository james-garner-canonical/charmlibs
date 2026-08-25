# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for the testing library from a Mode.APP_AND_UNIT requirer charm's perspective.

The charm holds a certificate in each scope, requested through
`certificate_requests_by_mode`. The library keeps one private key per scope, so the
fixture needs a key secret for each -- and only the leader can touch the app half.

There is no non-leader test here yet: on the library version this package pins, a
non-leader APP_AND_UNIT unit raises RelationDataAccessError before it can reconcile.
Add one once the fix lands -- such a unit should get its unit certificate and no
application certificate.
"""

import ops
import ops.testing

import charmlibs.interfaces.tls_certificates as tls_certificates
import charmlibs.interfaces.tls_certificates_testing as tls_certificates_testing
import requirer_charm_app_and_unit


def _state() -> ops.testing.State:
    relation = tls_certificates_testing.relation_for_requirer(
        endpoint="certificates",
        mode=tls_certificates.Mode.APP_AND_UNIT,
        certificate_requests_by_mode=requirer_charm_app_and_unit.REQUESTS_BY_MODE,
    )
    # One secret per scope, both holding DEFAULT_PRIVATE_KEY, which is what the fixture
    # signed both scopes' requests with.
    secrets = [
        tls_certificates_testing.private_key_secret(
            "certificates", mode=tls_certificates.Mode.APP
        ),
        tls_certificates_testing.private_key_secret(
            "certificates", mode=tls_certificates.Mode.UNIT
        ),
    ]
    # The app scope is leader-only, so these tests run as leader.
    return ops.testing.State(leader=True, relations=[relation], secrets=secrets)


def test_app_and_unit_requirer_leader_gets_both_certificates():
    ctx = ops.testing.Context(
        requirer_charm_app_and_unit.AppAndUnitRequirerCharm,
        meta=requirer_charm_app_and_unit.META,
    )
    with ctx(ctx.on.update_status(), _state()) as manager:
        state_out = manager.run()
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)
    assert manager.charm.app_certs is not None
    assert manager.charm.unit_certs is not None
    assert {c.common_name for c in manager.charm.app_certs} == {
        r.common_name for r in requirer_charm_app_and_unit.APP_REQUESTS
    }
    assert {c.common_name for c in manager.charm.unit_certs} == {
        r.common_name for r in requirer_charm_app_and_unit.UNIT_REQUESTS
    }


def test_app_and_unit_fixture_is_stable_across_reconciles():
    """Neither scope's requests may be discarded as unmatched on the charm's next run.

    This is the APP_AND_UNIT version of the coupling every requirer fixture has: get the
    split wrong and the library quietly rewrites the databag, leaving no certificates.
    """
    ctx = ops.testing.Context(
        requirer_charm_app_and_unit.AppAndUnitRequirerCharm,
        meta=requirer_charm_app_and_unit.META,
    )
    state = _state()
    relation = next(iter(state.relations))
    assert isinstance(relation, ops.testing.Relation)
    original = (
        relation.local_app_data["certificate_signing_requests"],
        relation.local_unit_data["certificate_signing_requests"],
    )
    for _ in range(2):
        state = ctx.run(ctx.on.relation_changed(state.get_relations("certificates")[0]), state)
        relation_out = state.get_relations("certificates")[0]
        assert (
            relation_out.local_app_data["certificate_signing_requests"],
            relation_out.local_unit_data["certificate_signing_requests"],
        ) == original
