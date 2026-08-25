# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

import dataclasses
import datetime
import typing

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from ops import testing

from charmlibs.interfaces import tls_certificates

from . import _raw

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

DEFAULT_PRIVATE_KEY = tls_certificates.PrivateKey(raw=_raw.KEY)
"""The private key the requirer fixtures sign certificate signing requests with.

The charm under test must use this key too, or its requests won't match the fixture's
certificates -- see :func:`relation_for_requirer` for how to arrange that.

Only the symbol is API. Its value is not: the key (like the testing CA's key and
certificate) may be regenerated in any release, so don't depend on the bytes -- for
example by snapshot-testing relation data, which embeds the CSRs and therefore the key.
Assert on parsed values via the library's accessors instead; not having to touch the
wire format is the point of this package.
"""
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


@dataclasses.dataclass(frozen=True)
class _DeniedRequest:
    """A certificate request the provider has answered with an error. See :func:`denied`."""

    request: tls_certificates.CertificateRequestAttributes
    error: tls_certificates.CertificateError


def denied(
    request: tls_certificates.CertificateRequestAttributes,
    *,
    code: tls_certificates.CertificateRequestErrorCode = (
        tls_certificates.CertificateRequestErrorCode.OTHER
    ),
    message: str = "Denied by the simulated provider.",
    reason: str | None = None,
) -> _DeniedRequest:
    """Mark a certificate request as denied by the provider.

    Pass the result in ``certificate_requests`` in place of the bare request::

        relation_for_requirer("certificates", certificate_requests=[
            REQUEST_A,  # issued as usual
            tls_certificates_testing.denied(
                REQUEST_B,
                code=tls_certificates.CertificateRequestErrorCode.DOMAIN_NOT_ALLOWED,
            ),
        ])

    The request still appears in the requirer's databag -- the charm asked -- but instead
    of a certificate the provider records an error for it, which the requirer library
    surfaces through ``get_request_errors()``/``get_request_error()`` and the
    ``certificate_denied`` event.

    Args:
        request: The request the provider denies.
        code: The error code the provider reports.
        message: The human-readable error message the provider reports.
        reason: Optional further detail, carried in the error's ``reason`` field.

    Returns:
        A wrapper accepted by ``certificate_requests`` in :func:`relation_for_requirer`
        and :func:`relation_for_provider`.
    """
    error = tls_certificates.CertificateError(
        code=code.value, name=code.name, message=message, reason=reason
    )
    return _DeniedRequest(request=request, error=error)


@dataclasses.dataclass(frozen=True)
class _AgedRequest:
    """A request answered with a back-dated certificate. See :func:`renewing`/:func:`expired`."""

    request: tls_certificates.CertificateRequestAttributes
    age: float
    """Fraction of the certificate's validity period already elapsed. Must be positive."""


def renewing(
    request: tls_certificates.CertificateRequestAttributes,
    *,
    renewal_relative_time: float = 0.9,
) -> _AgedRequest:
    """Mark a certificate request as answered with a certificate that is due for renewal.

    Pass the result in ``certificate_requests`` in place of the bare request. The
    certificate is issued back-dated, far enough through its validity period that the
    library's renewal safety net fires on the charm's next reconcile: the charm withdraws
    the request and replaces it with a fresh one for the provider to answer -- which
    :func:`respond_to_requests` can then do, completing the renewal.

    To model *every* certificate being stale, wrap each request::

        relation_for_requirer(
            "certificates", certificate_requests=[renewing(r) for r in REQUESTS]
        )

    Args:
        request: The request the provider answered with a soon-to-expire certificate.
        renewal_relative_time: Must match the ``renewal_relative_time`` the charm passes
            to ``TLSCertificatesRequiresV4``, which is where this default comes from. The
            library renews from slightly after that point; the certificate is back-dated
            to halfway between the renewal threshold and expiry.

    Returns:
        A wrapper accepted by ``certificate_requests`` in :func:`relation_for_requirer`
        and :func:`relation_for_provider`.
    """
    # The library's safety net renews from min(0.99, renewal_relative_time + 0.05) of the
    # validity period through to expiry; the secret-expiry path starts earlier, at
    # renewal_relative_time itself. Aim halfway between the safety threshold and expiry
    # to be comfortably inside both windows regardless of rounding.
    threshold = min(0.99, renewal_relative_time + 0.05)
    return _AgedRequest(request=request, age=(threshold + 1.0) / 2)


def expired(request: tls_certificates.CertificateRequestAttributes) -> _AgedRequest:
    """Mark a certificate request as answered with a certificate that has expired.

    Pass the result in ``certificate_requests`` in place of the bare request. The
    certificate is issued back-dated so that its entire validity period is in the past.

    Note the library currently keeps an expired certificate assigned and does not
    re-request it: its renewal safety net stops at expiry. This wrapper models the
    relation state; what a charm should do about it is up to the charm.

    Args:
        request: The request the provider answered with a now-expired certificate.

    Returns:
        A wrapper accepted by ``certificate_requests`` in :func:`relation_for_requirer`
        and :func:`relation_for_provider`.
    """
    return _AgedRequest(request=request, age=1.5)


@dataclasses.dataclass(frozen=True)
class _RevokedRequest:
    """A request whose issued certificate the provider has revoked. See :func:`revoked`."""

    request: tls_certificates.CertificateRequestAttributes


def revoked(request: tls_certificates.CertificateRequestAttributes) -> _RevokedRequest:
    """Mark a certificate request as answered with a certificate since revoked.

    Pass the result in ``certificate_requests`` in place of the bare request. The
    certificate is published with the relation's ``revoked`` flag set, which makes the
    requirer library remove the certificate's Juju secret on the next reconcile.

    Args:
        request: The request whose certificate the provider has revoked.

    Returns:
        A wrapper accepted by ``certificate_requests`` in :func:`relation_for_requirer`
        and :func:`relation_for_provider`.
    """
    return _RevokedRequest(request=request)


_CertificateRequest: typing.TypeAlias = (
    tls_certificates.CertificateRequestAttributes | _DeniedRequest | _AgedRequest | _RevokedRequest
)


@dataclasses.dataclass(frozen=True)
class _ResolvedRequest:
    """A certificate request signed into a CSR, together with its requested outcome."""

    csr: tls_certificates.CertificateSigningRequest
    is_ca: bool = False
    age: float = 0.0
    revoked: bool = False
    error: tls_certificates.CertificateError | None = None


def relation_for_requirer(
    # testing.Relation args
    endpoint: str,
    *,
    # charmlibs.interfaces.tls_certificates args
    mode: tls_certificates.Mode = tls_certificates.Mode.UNIT,
    certificate_requests: Iterable[_CertificateRequest] = (_REQUEST,),
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
        certificate_requests: The requests the requirer has made. A bare
            ``CertificateRequestAttributes`` is answered with a certificate (a CA
            certificate, for a request with ``is_ca=True``); wrap an entry with
            :func:`denied` to have the provider answer it with an error instead, with
            :func:`renewing`/:func:`expired` to answer it with a certificate late in or
            past its validity period, or with :func:`revoked` to answer it with a
            certificate marked as revoked -- all in the same relation as its issued
            neighbours.
        response: Whether the provider has answered. Pass ``False`` to populate only the
            requirer's side, modelling a request the provider hasn't issued a certificate for
            yet. Note the requirer's requests are present either way, so a relation from this
            function always implies the charm already holds a private key.

    Returns:
        An ``ops.testing.Relation`` to include in ``ops.testing.State(relations=...)``.
    """
    kwargs: _RelationKwargs = {}
    resolved = _split_requests(certificate_requests, key=DEFAULT_PRIVATE_KEY)
    # local requirer
    if mode is tls_certificates.Mode.APP:
        kwargs["local_app_data"] = _dump_requirer(resolved)
    else:
        kwargs["local_unit_data"] = _dump_requirer(resolved)
    # remote provider
    if response:
        kwargs["remote_app_data"] = _dump_provider(resolved)
    return _relation(endpoint, kwargs=kwargs)


def relation_for_provider(
    # testing.Relation args
    endpoint: str,
    *,
    # charmlibs.interfaces.tls_certificates args
    mode: tls_certificates.Mode = tls_certificates.Mode.UNIT,
    certificate_requests: Iterable[_CertificateRequest] = (_REQUEST,),
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
        certificate_requests: The requests the remote requirer has made. A bare
            ``CertificateRequestAttributes`` is one this charm has issued a certificate
            for (when ``response=True``); wrap an entry with :func:`denied` to model this
            charm having answered it with an error instead, with
            :func:`renewing`/:func:`expired` to model it having issued a certificate late
            in or past its validity period, or with :func:`revoked` to model it having
            revoked the certificate it issued.
        private_key: The remote requirer's key, used to sign its requests. Free to choose.
        response: Whether the provider charm has answered. Pass ``False`` to populate only the
            remote requirer's side, modelling requests this charm hasn't issued certificates for
            yet.

    Returns:
        An ``ops.testing.Relation`` to include in ``ops.testing.State(relations=...)``.
    """
    kwargs: _RelationKwargs = {}
    resolved = _split_requests(certificate_requests, key=private_key)
    # remote requirer
    if mode is tls_certificates.Mode.APP:
        kwargs["remote_app_data"] = _dump_requirer(resolved)
    else:
        kwargs["remote_units_data"] = {0: _dump_requirer(resolved)}
    # local provider
    if response:
        kwargs["local_app_data"] = _dump_provider(resolved)
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


def respond_to_requests(relation: testing.Relation) -> testing.Relation:
    """Return a copy of ``relation`` with the provider answering the CSRs currently present.

    :func:`relation_for_requirer` builds a static snapshot before the charm runs, so it
    cannot answer requests the charm makes *during* a test -- after key rotation, or
    certificate renewal, the charm withdraws its old CSRs and writes new ones, and nothing
    has issued certificates for those. This function plays the provider's next move: pass
    the relation from the output state, and every CSR the requirer currently has on the
    relation gets a certificate in the returned copy. Build the next input state with it
    to observe the charm picking the new certificates up::

        state = ctx.run(ctx.on.update_status(), state)  # charm rotates its key
        relation = state.get_relations("certificates")[0]
        state = dataclasses.replace(
            state, relations={tls_certificates_testing.respond_to_requests(relation)}
        )
        state = ctx.run(ctx.on.relation_changed(relation), state)

    The certificates answer whatever CSRs are present, so unlike
    :func:`relation_for_requirer` this is key-agnostic: it serves charms using
    :data:`DEFAULT_PRIVATE_KEY`, charms that just rotated to a fresh key, and
    charm-managed keys alike.

    Args:
        relation: A relation whose *local* side holds the requirer's certificate signing
            requests -- typically taken from the output state of a previous run of a
            requirer charm. Both databag locations are read, so any ``Mode`` works.

    Returns:
        A copy of ``relation``, with the remote provider's application data holding a
        certificate for each of the requirer's current certificate signing requests.
    """
    resolved = [
        _ResolvedRequest(
            csr=tls_certificates.CertificateSigningRequest.from_string(
                entry.certificate_signing_request
            ),
            is_ca=bool(entry.ca),
        )
        for databag in (relation.local_app_data, relation.local_unit_data)
        if "certificate_signing_requests" in databag
        for entry in tls_certificates._tls_certificates._RequirerData.load(
            databag
        ).certificate_signing_requests
    ]
    return dataclasses.replace(relation, remote_app_data=_dump_provider(resolved))


def _split_requests(
    certificate_requests: Iterable[_CertificateRequest],
    key: tls_certificates.PrivateKey,
) -> list[_ResolvedRequest]:
    """Sign each request with ``key``, keeping each one's requested outcome alongside."""
    resolved: list[_ResolvedRequest] = []
    for item in certificate_requests:
        attributes = (
            item
            if isinstance(item, tls_certificates.CertificateRequestAttributes)
            else item.request
        )
        csr = tls_certificates.CertificateSigningRequest.generate(
            attributes=attributes, private_key=key
        )
        is_ca = attributes.is_ca
        if isinstance(item, _DeniedRequest):
            resolved.append(_ResolvedRequest(csr=csr, is_ca=is_ca, error=item.error))
        elif isinstance(item, _AgedRequest):
            resolved.append(_ResolvedRequest(csr=csr, is_ca=is_ca, age=item.age))
        elif isinstance(item, _RevokedRequest):
            resolved.append(_ResolvedRequest(csr=csr, is_ca=is_ca, revoked=True))
        else:
            resolved.append(_ResolvedRequest(csr=csr, is_ca=is_ca))
    return resolved


def _dump_requirer(resolved: Iterable[_ResolvedRequest]) -> dict[str, str]:
    requirer = tls_certificates._tls_certificates._RequirerData(
        certificate_signing_requests=[
            tls_certificates._tls_certificates._CertificateSigningRequest(
                certificate_signing_request=str(request.csr).strip(),
                ca=request.is_ca,
            )
            for request in resolved
        ]
    )
    ret: dict[str, str] = {}
    requirer.dump(ret)
    return ret


def _dump_provider(resolved: Iterable[_ResolvedRequest]) -> dict[str, str]:
    certificates: list[tls_certificates._tls_certificates._Certificate] = []
    request_errors: list[tls_certificates._tls_certificates._RequestError] = []
    for request in resolved:
        if request.error is not None:
            request_errors.append(
                tls_certificates._tls_certificates._RequestError(
                    csr=str(request.csr), error=request.error
                )
            )
            continue
        certificate = _sign(request.csr, age=request.age, is_ca=request.is_ca)
        certificates.append(
            tls_certificates._tls_certificates._Certificate(
                certificate=str(certificate),
                certificate_signing_request=str(request.csr),
                ca=str(_CA_CERT),
                # leaf to root, the order chain_has_valid_order expects
                chain=[str(certificate), str(_CA_CERT)],
                revoked=True if request.revoked else None,
            )
        )
    provider = tls_certificates._tls_certificates._ProviderApplicationData(
        certificates=certificates, request_errors=request_errors
    )
    ret: dict[str, str] = {}
    provider.dump(ret)
    return ret


_VALIDITY = datetime.timedelta(days=42)


def _sign(
    csr: tls_certificates.CertificateSigningRequest, age: float = 0.0, is_ca: bool = False
) -> tls_certificates.Certificate:
    certificate = csr.sign(ca=_CA_CERT, ca_private_key=_CA_KEY, validity=_VALIDITY, is_ca=is_ca)
    if not age:
        return certificate
    return _backdate(certificate, age=age)


def _backdate(
    certificate: tls_certificates.Certificate, age: float
) -> tls_certificates.Certificate:
    """Re-issue ``certificate`` with ``age`` of its validity period already elapsed.

    The library computes renewal as a fraction of ``validity_end - validity_start``, and
    ``Certificate.generate`` hardcodes ``not_valid_before`` to the time of issue, so aged
    certificates can only be built by hand: sign through the library as usual (keeping
    its extension handling), then rebuild the result with shifted validity dates and
    everything else copied verbatim, re-signed by the same testing CA.
    """
    cert = x509.load_pem_x509_certificate(str(certificate).encode())
    not_valid_before = datetime.datetime.now(datetime.timezone.utc) - _VALIDITY * age
    builder = x509.CertificateBuilder(
        subject_name=cert.subject,
        issuer_name=cert.issuer,
        public_key=cert.public_key(),
        serial_number=cert.serial_number,
        not_valid_before=not_valid_before,
        not_valid_after=not_valid_before + _VALIDITY,
    )
    for extension in cert.extensions:
        builder = builder.add_extension(extension.value, extension.critical)
    ca_key = serialization.load_pem_private_key(str(_CA_KEY).encode(), password=None)
    assert isinstance(ca_key, rsa.RSAPrivateKey)  # the testing CA is RSA
    backdated = builder.sign(ca_key, hashes.SHA256())
    return tls_certificates.Certificate.from_string(
        backdated.public_bytes(serialization.Encoding.PEM).decode()
    )


def _relation(endpoint: str, kwargs: _RelationKwargs) -> testing.Relation:
    return testing.Relation(endpoint, interface=_INTERFACE_NAME, **kwargs)
