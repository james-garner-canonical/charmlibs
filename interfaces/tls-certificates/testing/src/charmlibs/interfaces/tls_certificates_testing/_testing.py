# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

import datetime
import typing

from ops import testing

from charmlibs.interfaces import tls_certificates

from . import _raw

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

DEFAULT_PRIVATE_KEY = tls_certificates.PrivateKey(raw=_raw.KEY)
_INTERFACE_NAME = "tls-certificates"
_LIBID = tls_certificates._tls_certificates.LIBID
_REQUEST = tls_certificates.CertificateRequestAttributes(common_name="example.com")
_CA_CERT = tls_certificates.Certificate(raw=_raw.CERT)
_CA_KEY = tls_certificates.PrivateKey(raw=_raw.CA_KEY)


class _RelationKwargs(typing.TypedDict, total=False):
    local_app_data: dict[str, str]
    local_unit_data: dict[str, str]
    remote_app_data: dict[str, str]
    remote_units_data: dict[int, dict[str, str]]


def relation_for_requirer(
    # testing.Relation args
    endpoint: str,
    *,
    # charmlibs.interfaces.tls_certificates args
    mode: tls_certificates.Mode = tls_certificates.Mode.UNIT,
    certificate_requests: Iterable[tls_certificates.CertificateRequestAttributes] = (_REQUEST,),
    # interface 'conversation' args
    response: bool = True,
) -> testing.Relation:
    """Return a relation for testing a requirer charm.

    By default this models a typical, fully answered relation: the requirer has made
    ``certificate_requests``, and the provider has issued a certificate for each.

    The requests are signed with :data:`DEFAULT_PRIVATE_KEY`, so the charm under test must use
    that key too, or its own requests won't match the issued certificates. There is deliberately
    no argument for the charm's key -- point the charm at :data:`DEFAULT_PRIVATE_KEY` instead:

    - If the library manages the charm's key (the recommended configuration), add
      :func:`private_key_secret` to ``ops.testing.State(secrets=...)``.
    - If the charm passes ``private_key`` to ``TLSCertificatesRequiresV4``, supply
      :data:`DEFAULT_PRIVATE_KEY` through whatever seam the charm already uses for its key.

    Args:
        endpoint: The charm's endpoint name for this relation.
        mode: Must match the ``mode`` passed to ``TLSCertificatesRequiresV4``. ``Mode.APP``
            puts the requests in the application databag, anything else in the unit databag.
        certificate_requests: The requests the requirer has made.
        response: Whether the provider has answered. Pass ``False`` to populate only the
            requirer's side, modelling a request the provider hasn't issued a certificate for
            yet. Note the requirer's requests are present either way, so a relation from this
            function always implies the charm already holds a private key.

    Returns:
        An ``ops.testing.Relation`` to include in ``ops.testing.State(relations=...)``.
    """
    kwargs: _RelationKwargs = {}
    csrs = _make_csrs(certificate_requests, key=DEFAULT_PRIVATE_KEY)
    # local requirer
    if mode is tls_certificates.Mode.APP:
        kwargs["local_app_data"] = _dump_requirer(csrs)
    else:
        kwargs["local_unit_data"] = _dump_requirer(csrs)
    # remote provider
    if response:
        kwargs["remote_app_data"] = _dump_provider(csrs)
    return _relation(endpoint, kwargs=kwargs)


def relation_for_provider(
    # testing.Relation args
    endpoint: str,
    *,
    # charmlibs.interfaces.tls_certificates args
    mode: tls_certificates.Mode = tls_certificates.Mode.UNIT,
    certificate_requests: Iterable[tls_certificates.CertificateRequestAttributes] = (_REQUEST,),
    private_key: tls_certificates.PrivateKey = DEFAULT_PRIVATE_KEY,
    # interface 'conversation' args
    response: bool = True,
) -> testing.Relation:
    """Return a relation for testing a provider charm.

    By default this models a typical, fully answered relation: a remote requirer has made
    ``certificate_requests``, and the provider charm under test has issued a certificate for each.

    Unlike :func:`relation_for_requirer`, ``private_key`` here belongs to the *simulated remote
    requirer*, mirroring ``TLSCertificatesRequiresV4(private_key=...)`` on the other end of the
    relation. It is ordinary fixture configuration: nothing else needs to know it, and a provider
    charm never sees it. ``TLSCertificatesProvidesV4`` manages no private key of its own, so no
    key needs seeding for the charm under test.

    Args:
        endpoint: The charm's endpoint name for this relation.
        mode: Must match the ``mode`` used by the remote requirer. ``Mode.APP`` puts its requests
            in the remote application databag, anything else in the remote unit databag.
        certificate_requests: The requests the remote requirer has made.
        private_key: The remote requirer's key, used to sign its requests. Free to choose.
        response: Whether the provider charm has answered. Pass ``False`` to populate only the
            remote requirer's side, modelling requests this charm hasn't issued certificates for
            yet.

    Returns:
        An ``ops.testing.Relation`` to include in ``ops.testing.State(relations=...)``.
    """
    kwargs: _RelationKwargs = {}
    csrs = _make_csrs(certificate_requests, key=private_key)
    # remote requirer
    if mode is tls_certificates.Mode.APP:
        kwargs["remote_app_data"] = _dump_requirer(csrs)
    else:
        kwargs["remote_units_data"] = {0: _dump_requirer(csrs)}
    # local provider
    if response:
        kwargs["local_app_data"] = _dump_provider(csrs)
    return _relation(endpoint, kwargs=kwargs)


# Why seeding a secret, rather than any of the more obvious alternatives? All of these were
# tried and measured against a charm that lets the library manage its key:
#
# - Patching `Certificate.matches_private_key` to always pass. Doesn't work: the CSR string
#   equality gate below fails first, so the certificate is never even considered. Neutering
#   that too would mean faking the entire lookup.
# - Pinning `PrivateKey.generate` to a fixed key. Works, but only on events that run the
#   library's `_configure` -- `update_status` gets no key at all. It also relies on a starting
#   state Juju could never produce: requests in the databag but no key secret, when the charm
#   could not have made those requests without first generating a key. Strictly less capable
#   than seeding, for no less coupling.
# - A helper returning a whole `ops.testing.State`. Doesn't compose for charms with several
#   relations across different interfaces.
# - An autouse pytest fixture pinning the key. Actively harmful: `regenerate_private_key()`
#   generates through the same path, so rotation would return the *same* key and any test
#   asserting the key changed would silently pass while testing nothing.
def private_key_secret(
    # testing.Relation args
    endpoint: str,
    *,
    # charmlibs.interfaces.tls_certificates args
    mode: tls_certificates.Mode = tls_certificates.Mode.UNIT,
    private_key: tls_certificates.PrivateKey = DEFAULT_PRIVATE_KEY,
    # ops.testing args
    unit_id: int = 0,
) -> testing.Secret:
    """Return the Juju secret holding the requirer's library-managed private key.

    Charms that let the library manage their private key -- the recommended configuration --
    need this alongside :func:`relation_for_requirer`. Without it the library has no key, and
    silently resolves no certificates.

    The returned secret sits at the label the library itself would have used, so the library
    adopts ``private_key`` as its own managed key via its normal lookup path. Pass the same
    ``endpoint``, ``mode`` and ``private_key`` used to build the relation.

    Charms that pass ``private_key`` to ``TLSCertificatesRequiresV4`` should NOT use this: the
    library deletes the managed secret when the charm supplies its own key.

    Args:
        endpoint: The charm's endpoint name for this relation.
        mode: Must match the ``mode`` passed to ``TLSCertificatesRequiresV4``. ``Mode.APP``
            produces an app-owned secret; anything else a unit-owned one.
        private_key: The key to seed. Must match the one used to build the relation.
        unit_id: Must match the ``unit_id`` of the ``ops.testing.Context`` under test. In
            ``Mode.UNIT`` the label embeds the unit number, and a mismatch surfaces as
            "no certificates" rather than an error.

    Returns:
        An ``ops.testing.Secret`` to include in ``ops.testing.State(secrets=...)``.
    """
    # The library matches a provider certificate to a request on two gates: the CSR strings must
    # be equal, and `certificate.matches_private_key(key)` must hold for the requirer's key. Both
    # fail if the charm's key differs from the one the relation's requests were signed with -- and
    # both fail silently, as "no certificates" rather than an error. Hence this helper: it seeds
    # the key at the label the library looks the key up under, so the two agree.
    if mode is tls_certificates.Mode.APP:
        label = f"{_LIBID}-private-key-app-{endpoint}"
        owner = "app"
    else:
        label = f"{_LIBID}-private-key-{unit_id}-{endpoint}"
        owner = "unit"
    return testing.Secret(
        tracked_content={"private-key": str(private_key)}, label=label, owner=owner
    )


def _make_csrs(
    certificate_requests: Iterable[tls_certificates.CertificateRequestAttributes],
    key: tls_certificates.PrivateKey,
) -> list[tls_certificates.CertificateSigningRequest]:
    return [
        tls_certificates.CertificateSigningRequest.generate(attributes=r, private_key=key)
        for r in certificate_requests
    ]


def _dump_requirer(csrs: Iterable[tls_certificates.CertificateSigningRequest]) -> dict[str, str]:
    requirer = tls_certificates._tls_certificates._RequirerData(
        certificate_signing_requests=[
            tls_certificates._tls_certificates._CertificateSigningRequest(
                certificate_signing_request=str(csr).strip(),
                ca=False,
            )
            for csr in csrs
        ]
    )
    ret: dict[str, str] = {}
    requirer.dump(ret)
    return ret


def _dump_provider(
    csrs: Iterable[tls_certificates.CertificateSigningRequest],
) -> dict[str, str]:
    provider = tls_certificates._tls_certificates._ProviderApplicationData(
        certificates=[
            tls_certificates._tls_certificates._Certificate(
                certificate=str(_sign(csr)),
                certificate_signing_request=str(csr),
                ca=str(_CA_CERT),
                chain=[],
            )
            for csr in csrs
        ]
    )
    ret: dict[str, str] = {}
    provider.dump(ret)
    return ret


def _sign(csr: tls_certificates.CertificateSigningRequest) -> tls_certificates.Certificate:
    return csr.sign(ca=_CA_CERT, ca_private_key=_CA_KEY, validity=datetime.timedelta(days=42))


def _relation(endpoint: str, kwargs: _RelationKwargs) -> testing.Relation:
    return testing.Relation(endpoint, interface=_INTERFACE_NAME, **kwargs)
