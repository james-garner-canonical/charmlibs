# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

import dataclasses
import datetime
import types
import typing

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from ops import testing

from charmlibs.interfaces import tls_certificates

# The library's private module. Building relation data means writing the interface's wire
# format, which is private: the pydantic models below, the databag encoding, the secret
# labels and the renewal threshold all live here. Reusing them is deliberate -- this package
# and the library are released in lockstep and pin each other exactly, so they cannot drift,
# whereas a second copy of the wire format could. Every use is covered by a test.
from charmlibs.interfaces.tls_certificates import _tls_certificates as _internal

from . import _raw

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

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
_REQUEST = tls_certificates.CertificateRequestAttributes(common_name="example.com")
_APP_REQUEST = tls_certificates.CertificateRequestAttributes(common_name="app.example.com")
_UNIT_REQUEST = tls_certificates.CertificateRequestAttributes(common_name="unit.example.com")
_CA_CERT = tls_certificates.Certificate(raw=_raw.CERT)
_CA_KEY = tls_certificates.PrivateKey(raw=_raw.CA_KEY)
_SINGLE_UNIT = (0,)


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
) -> CertificateRequest:
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
        A :data:`CertificateRequest` accepted by ``certificate_requests`` in
        :func:`relation_for_requirer` and :func:`relation_for_provider`.
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
) -> CertificateRequest:
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
            certificate is back-dated to halfway between the library's renewal threshold
            for that value and expiry.

    Returns:
        A :data:`CertificateRequest` accepted by ``certificate_requests`` in
        :func:`relation_for_requirer` and :func:`relation_for_provider`.
    """
    # The threshold comes from the library itself rather than a copy of its formula, so
    # that changing it there can't leave this fixture quietly failing to trigger renewal.
    # The library's safety net renews from the threshold through to expiry; the
    # secret-expiry path starts earlier, at renewal_relative_time itself. Aim halfway
    # between the threshold and expiry to be comfortably inside both windows.
    threshold = _internal._renewal_safety_threshold(renewal_relative_time)
    return _AgedRequest(request=request, age=(threshold + 1.0) / 2)


def expired(request: tls_certificates.CertificateRequestAttributes) -> CertificateRequest:
    """Mark a certificate request as answered with a certificate that has expired.

    Pass the result in ``certificate_requests`` in place of the bare request. The
    certificate is issued back-dated so that its entire validity period is in the past.

    Note the library currently keeps an expired certificate assigned and does not
    re-request it: its renewal safety net stops at expiry. This wrapper models the
    relation state; what a charm should do about it is up to the charm.

    Args:
        request: The request the provider answered with a now-expired certificate.

    Returns:
        A :data:`CertificateRequest` accepted by ``certificate_requests`` in
        :func:`relation_for_requirer` and :func:`relation_for_provider`.
    """
    return _AgedRequest(request=request, age=1.5)


@dataclasses.dataclass(frozen=True)
class _RevokedRequest:
    """A request whose issued certificate the provider has revoked. See :func:`revoked`."""

    request: tls_certificates.CertificateRequestAttributes


def revoked(request: tls_certificates.CertificateRequestAttributes) -> CertificateRequest:
    """Mark a certificate request as answered with a certificate since revoked.

    Pass the result in ``certificate_requests`` in place of the bare request. The
    certificate is published with the relation's ``revoked`` flag set, which makes the
    requirer library remove the certificate's Juju secret on the next reconcile.

    Args:
        request: The request whose certificate the provider has revoked.

    Returns:
        A :data:`CertificateRequest` accepted by ``certificate_requests`` in
        :func:`relation_for_requirer` and :func:`relation_for_provider`.
    """
    return _RevokedRequest(request=request)


CertificateRequest: typing.TypeAlias = (
    tls_certificates.CertificateRequestAttributes | _DeniedRequest | _AgedRequest | _RevokedRequest
)
"""An entry in ``certificate_requests``: a request, and what the provider did about it.

A bare ``tls_certificates.CertificateRequestAttributes`` is a request the provider
answered with a certificate; :func:`denied`, :func:`renewing`, :func:`expired` and
:func:`revoked` return the other outcomes. The wrapper types themselves are opaque --
build them with those functions, and use this alias to annotate mixed lists::

    requests: list[tls_certificates_testing.CertificateRequest] = [
        REQUEST_A, tls_certificates_testing.denied(REQUEST_B)
    ]
"""

# FIXME: this private name appears in the public signatures of relation_for_requirer and
# relation_for_provider, so callers see a type they can't import. Spelling it out inline
# would fix that -- every part of it is public. Left alone for now to match the library,
# which leaks _CertificateRequestsArg and _CertificateRequestsByModeArg from the public
# TLSCertificatesRequiresV4.__init__ in the same way; fix both together.
# Reusing the library's _CertificateRequestsByMode is not an option: its values are
# list[CertificateRequestAttributes], which excludes the wrapped outcomes above.
_Scope: typing.TypeAlias = "typing.Literal[tls_certificates.Mode.APP, tls_certificates.Mode.UNIT]"
"""The two scopes a certificate request can belong to, as the library names them."""
_RequestsByMode: typing.TypeAlias = "Mapping[_Scope, Iterable[CertificateRequest]]"


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
    certificate_requests: Iterable[CertificateRequest] | None = None,
    certificate_requests_by_mode: _RequestsByMode | None = None,
    capabilities: tls_certificates.ProviderCapabilities | None = None,
    # ops.testing args
    remote_app_name: str = "remote",
    remote_unit_ids: Iterable[int] = _SINGLE_UNIT,
    # interface 'conversation' args
    response: bool = True,
) -> testing.Relation:
    """Return a relation for testing a requirer charm.

    By default this models a typical, fully answered relation: the requirer has made
    ``certificate_requests``, and the provider has issued a certificate for each.

    Two things must agree with the charm under test, and both fail *silently* if they
    don't -- the library discards data it can't match, and the charm simply sees no
    certificates:

    - **The requests.** Pass the same ``CertificateRequestAttributes`` the charm passes to
      ``TLSCertificatesRequiresV4``. On its next reconcile the library removes any request
      in the databag that doesn't match one of its own, and nothing has issued a
      certificate for the ones it writes in their place.
    - **The private key.** The requests are signed with :data:`DEFAULT_PRIVATE_KEY`, so the
      charm must use that key too. There is deliberately no argument for the charm's key --
      point the charm at :data:`DEFAULT_PRIVATE_KEY` instead:

      - If the library manages the charm's key (the recommended configuration), add
        :func:`private_key_secret` to ``ops.testing.State(secrets=...)``.
      - If the charm passes ``private_key`` to ``TLSCertificatesRequiresV4``, supply
        :data:`DEFAULT_PRIVATE_KEY` through whatever seam the charm already uses for its key.

    To avoid both couplings entirely, start from a bare ``ops.testing.Relation``, let the
    charm make its own requests with its own key, and answer them with
    :func:`respond_to_requests`. That needs no agreement of any kind, at the cost of an
    extra ``ctx.run``.

    Args:
        endpoint: The charm's endpoint name for this relation.
        mode: Must match the ``mode`` passed to ``TLSCertificatesRequiresV4``. ``Mode.APP``
            puts the requests in the application databag, ``Mode.UNIT`` in the unit databag,
            and ``Mode.APP_AND_UNIT`` splits them per ``certificate_requests_by_mode``.
        certificate_requests: The requests the requirer has made. A bare
            ``CertificateRequestAttributes`` is answered with a certificate (a CA
            certificate, for a request with ``is_ca=True``); wrap an entry with
            :func:`denied` to have the provider answer it with an error instead, with
            :func:`renewing`/:func:`expired` to answer it with a certificate late in or
            past its validity period, or with :func:`revoked` to answer it with a
            certificate marked as revoked -- all in the same relation as its issued
            neighbours. Must not be given when ``mode`` is ``Mode.APP_AND_UNIT``.
        certificate_requests_by_mode: The requests the requirer has made, per mode,
            mirroring ``TLSCertificatesRequiresV4(certificate_requests_by_mode=...)``.
            Required when ``mode`` is ``Mode.APP_AND_UNIT`` (where it defaults to one app
            and one unit request), and rejected otherwise. Keys must be ``Mode.APP`` and/or
            ``Mode.UNIT``; values take the same entries as ``certificate_requests``.
        capabilities: What the simulated provider has advertised about its certificate
            server. The default ``None`` models a provider that has not advertised
            anything, which ``get_provider_capabilities()`` reports as ``None`` ("not
            known yet"); pass a ``ProviderCapabilities`` -- even an empty one -- to model
            a provider that has, with each field carrying its own three-way meaning per
            the library's docs.
        remote_app_name: The name of the simulated provider application.
        remote_unit_ids: The unit numbers the simulated provider has on this relation. The
            provider writes only application data, so these units' databags are empty; they
            exist for charms that look at ``relation.units``.
        response: Whether the provider has answered. Pass ``False`` to populate only the
            requirer's side, modelling a request the provider hasn't issued a certificate for
            yet (``capabilities`` are still advertised if given -- a provider can advertise
            before it answers anything). Note the requirer's requests are present either
            way, so a relation from this function always implies the charm already holds a
            private key.

    Returns:
        An ``ops.testing.Relation`` to include in ``ops.testing.State(relations=...)``.

    Raises:
        ValueError: If ``certificate_requests`` and ``certificate_requests_by_mode`` are
            not used in the combination ``mode`` requires.
    """
    by_mode = _requests_by_mode(mode, certificate_requests, certificate_requests_by_mode)
    kwargs: _RelationKwargs = {}
    resolved: list[_ResolvedRequest] = []
    # local requirer
    if tls_certificates.Mode.APP in by_mode:
        app = _resolve_requests(by_mode[tls_certificates.Mode.APP], key=DEFAULT_PRIVATE_KEY)
        resolved.extend(app)
        kwargs["local_app_data"] = _dump_requirer(app)
    if tls_certificates.Mode.UNIT in by_mode:
        unit = _resolve_requests(by_mode[tls_certificates.Mode.UNIT], key=DEFAULT_PRIVATE_KEY)
        resolved.extend(unit)
        kwargs["local_unit_data"] = _dump_requirer(unit)
    # remote provider
    unit_ids = tuple(remote_unit_ids)
    if unit_ids != _SINGLE_UNIT:
        kwargs["remote_units_data"] = {unit_id: {} for unit_id in unit_ids}
    if response:
        kwargs["remote_app_data"] = _dump_provider(resolved, capabilities=capabilities)
    elif capabilities is not None:
        kwargs["remote_app_data"] = _dump_provider([], capabilities=capabilities)
    return _relation(endpoint, remote_app_name=remote_app_name, kwargs=kwargs)


def relation_for_provider(
    # testing.Relation args
    endpoint: str,
    *,
    # charmlibs.interfaces.tls_certificates args
    mode: tls_certificates.Mode = tls_certificates.Mode.UNIT,
    certificate_requests: Iterable[CertificateRequest] | None = None,
    certificate_requests_by_mode: _RequestsByMode | None = None,
    private_key: tls_certificates.PrivateKey = DEFAULT_PRIVATE_KEY,
    capabilities: tls_certificates.ProviderCapabilities | None = None,
    # ops.testing args
    remote_app_name: str = "remote",
    remote_unit_ids: Iterable[int] = _SINGLE_UNIT,
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
            in the remote application databag, ``Mode.UNIT`` in the remote unit databags, and
            ``Mode.APP_AND_UNIT`` splits them per ``certificate_requests_by_mode``.
        certificate_requests: The requests the remote requirer has made. A bare
            ``CertificateRequestAttributes`` is one this charm has issued a certificate
            for (when ``response=True``); wrap an entry with :func:`denied` to model this
            charm having answered it with an error instead, with
            :func:`renewing`/:func:`expired` to model it having issued a certificate late
            in or past its validity period, or with :func:`revoked` to model it having
            revoked the certificate it issued. Must not be given when ``mode`` is
            ``Mode.APP_AND_UNIT``.
        certificate_requests_by_mode: The remote requirer's requests, per mode, mirroring
            ``TLSCertificatesRequiresV4(certificate_requests_by_mode=...)``. Required when
            ``mode`` is ``Mode.APP_AND_UNIT`` (where it defaults to one app and one unit
            request), and rejected otherwise.
        private_key: The remote requirer's key, used to sign its requests. Free to choose.
            All remote units share it; their requests still differ, because the library
            gives each request a unique subject identifier by default. Requests built with
            ``add_unique_id_to_subject_name=False`` are identical across units, which is
            what a real deployment of such a requirer would also produce.
        capabilities: What this charm has already advertised about its certificate server,
            for testing a provider that starts with capabilities in its own databag --
            stale ones it should replace, say. A provider charm publishes its own
            capabilities when it runs, so leave this out unless the starting state matters.
        remote_app_name: The name of the simulated requirer application.
        remote_unit_ids: The unit numbers the simulated requirer has on this relation. In
            ``Mode.UNIT`` and ``Mode.APP_AND_UNIT`` each one makes its own copy of the
            requests, so a provider charm can be tested against a multi-unit requirer.
        response: Whether the provider charm has answered. Pass ``False`` to populate only the
            remote requirer's side, modelling requests this charm hasn't issued certificates for
            yet (``capabilities`` are still advertised if given).

    Returns:
        An ``ops.testing.Relation`` to include in ``ops.testing.State(relations=...)``.

    Raises:
        ValueError: If ``certificate_requests`` and ``certificate_requests_by_mode`` are
            not used in the combination ``mode`` requires.
    """
    by_mode = _requests_by_mode(mode, certificate_requests, certificate_requests_by_mode)
    kwargs: _RelationKwargs = {}
    resolved: list[_ResolvedRequest] = []
    # remote requirer
    if tls_certificates.Mode.APP in by_mode:
        app = _resolve_requests(by_mode[tls_certificates.Mode.APP], key=private_key)
        resolved.extend(app)
        kwargs["remote_app_data"] = _dump_requirer(app)
    unit_ids = tuple(remote_unit_ids)
    if tls_certificates.Mode.UNIT in by_mode:
        units: dict[int, dict[str, str]] = {}
        for unit_id in unit_ids:
            # Resolved once per unit: each unit signs its own requests, so (unless the
            # requests disable the unique subject id) each unit's CSRs are its own.
            unit = _resolve_requests(by_mode[tls_certificates.Mode.UNIT], key=private_key)
            resolved.extend(unit)
            units[unit_id] = _dump_requirer(unit)
        kwargs["remote_units_data"] = units
    elif unit_ids != _SINGLE_UNIT:
        kwargs["remote_units_data"] = {unit_id: {} for unit_id in unit_ids}
    # local provider
    if response:
        kwargs["local_app_data"] = _dump_provider(resolved, capabilities=capabilities)
    elif capabilities is not None:
        kwargs["local_app_data"] = _dump_provider([], capabilities=capabilities)
    return _relation(endpoint, remote_app_name=remote_app_name, kwargs=kwargs)


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

    This describes *one* secret, so ``Mode.APP_AND_UNIT`` is not accepted: the library keeps
    a separate key per scope there. Call this once per mode instead, seeding the same key in
    both, since :func:`relation_for_requirer` signs both scopes' requests with it::

        secrets = [
            private_key_secret("certificates", mode=tls_certificates.Mode.APP),
            private_key_secret("certificates", mode=tls_certificates.Mode.UNIT),
        ]

    Charms that pass ``private_key`` to ``TLSCertificatesRequiresV4`` should NOT use this: the
    library deletes the managed secret when the charm supplies its own key.

    Args:
        endpoint: The charm's endpoint name for this relation.
        mode: Must be ``Mode.APP`` or ``Mode.UNIT``, matching the scope of the key being
            seeded. ``Mode.APP`` produces an app-owned secret, ``Mode.UNIT`` a unit-owned one.
        private_key: The key to seed. Must match the one used to build the relation.
        unit_id: Must match the ``unit_id`` of the ``ops.testing.Context`` under test. In
            ``Mode.UNIT`` the label embeds the unit number, and a mismatch surfaces as
            "no certificates" rather than an error.

    Returns:
        An ``ops.testing.Secret`` to include in ``ops.testing.State(secrets=...)``.

    Raises:
        ValueError: If ``mode`` is ``Mode.APP_AND_UNIT``.
    """
    # The library matches a provider certificate to a request on two gates: the CSR strings must
    # be equal, and `certificate.matches_private_key(key)` must hold for the requirer's key. Both
    # fail if the charm's key differs from the one the relation's requests were signed with -- and
    # both fail silently, as "no certificates" rather than an error. Hence this helper: it seeds
    # the key at the label the library looks the key up under, so the two agree.
    if mode is tls_certificates.Mode.APP_AND_UNIT:
        raise ValueError(
            "private_key_secret describes a single secret, and Mode.APP_AND_UNIT uses one key "
            "per scope. Call it once with mode=Mode.APP and once with mode=Mode.UNIT."
        )
    owner = "app" if mode is tls_certificates.Mode.APP else "unit"
    # Derive the label with the library's own code rather than a copy of its format, so that
    # changing it there can't leave this helper seeding a secret the library never looks up.
    # The method reads only these two attributes off the requirer object.
    requirer = typing.cast(
        "tls_certificates.TLSCertificatesRequiresV4",
        types.SimpleNamespace(relationship_name=endpoint, _get_unit_number=lambda: str(unit_id)),
    )
    label = tls_certificates.TLSCertificatesRequiresV4._get_private_key_secret_label(
        requirer, mode
    )
    return testing.Secret(
        tracked_content={"private-key": str(private_key)}, label=label, owner=owner
    )


def respond_to_requests(relation: testing.Relation) -> testing.Relation:
    """Return a copy of ``relation`` with the provider answering any unanswered requests.

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

    Only requests the provider hasn't answered are issued for. Anything it has already
    published stays as it is -- advertised capabilities, recorded errors from
    :func:`denied`, and existing certificates with their :func:`renewing`, :func:`expired`
    and :func:`revoked` state -- so this is safe to call on a fully populated relation and
    safe to call repeatedly. Answers to requests the requirer has since withdrawn are
    dropped, which is what the provider library does too.

    The certificates answer whatever CSRs are present, so unlike
    :func:`relation_for_requirer` this is key-agnostic: it serves charms using
    :data:`DEFAULT_PRIVATE_KEY`, charms that just rotated to a fresh key, and
    charm-managed keys alike. Starting from a bare ``ops.testing.Relation`` and letting the
    charm make its own requests is the one way to build a requirer test that needs no
    agreement with the fixture at all.

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
        for entry in _internal._RequirerData.load(databag).certificate_signing_requests
    ]
    published = _load_provider(relation.remote_app_data)
    # Load-modify-dump: keep what the provider has already said, about requests that are
    # still on the relation, and add certificates only for the ones it hasn't answered.
    requested = {request.csr for request in resolved}
    certificates = [
        certificate
        for certificate in published.certificates
        if _as_csr(certificate.certificate_signing_request) in requested
    ]
    request_errors = [
        error for error in published.request_errors if _as_csr(error.csr) in requested
    ]
    answered = {_as_csr(entry.certificate_signing_request) for entry in certificates}
    answered |= {_as_csr(error.csr) for error in request_errors}
    certificates.extend(
        _certificate_entry(request) for request in resolved if request.csr not in answered
    )
    data = _internal._ProviderApplicationData(
        certificates=certificates,
        request_errors=request_errors,
        capabilities=published.capabilities,
    )
    ret: dict[str, str] = {}
    data.dump(ret)
    return dataclasses.replace(relation, remote_app_data=ret)


def _requests_by_mode(
    mode: tls_certificates.Mode,
    certificate_requests: Iterable[CertificateRequest] | None,
    certificate_requests_by_mode: _RequestsByMode | None,
) -> dict[tls_certificates.Mode, tuple[CertificateRequest, ...]]:
    """Validate the request arguments against ``mode`` and return them keyed by scope.

    Mirrors the pairing rules ``TLSCertificatesRequiresV4`` enforces on its own
    ``certificate_requests``/``certificate_requests_by_mode`` arguments, so a fixture can't
    be built in a shape the charm under test could not have produced.
    """
    app_and_unit = tls_certificates.Mode.APP_AND_UNIT
    if certificate_requests is not None and certificate_requests_by_mode is not None:
        raise ValueError(
            "certificate_requests and certificate_requests_by_mode are mutually exclusive."
        )
    if mode is app_and_unit:
        if certificate_requests is not None:
            raise ValueError(
                "certificate_requests must not be given when mode is Mode.APP_AND_UNIT; "
                "use certificate_requests_by_mode."
            )
        if certificate_requests_by_mode is None:
            certificate_requests_by_mode = {
                tls_certificates.Mode.APP: (_APP_REQUEST,),
                tls_certificates.Mode.UNIT: (_UNIT_REQUEST,),
            }
        # Iterate as plain Modes: the annotation rules APP_AND_UNIT out, but callers
        # without a type checker can still pass it, and it must not reach the databag.
        keys = typing.cast("Iterable[tls_certificates.Mode]", certificate_requests_by_mode)
        invalid = sorted(m.name for m in keys if m is app_and_unit)
        if invalid:
            raise ValueError(
                "certificate_requests_by_mode keys must be Mode.APP or Mode.UNIT, "
                f"not {', '.join(invalid)}."
            )
        return {m: tuple(requests) for m, requests in certificate_requests_by_mode.items()}
    if certificate_requests_by_mode is not None:
        raise ValueError(
            "certificate_requests_by_mode is only valid when mode is Mode.APP_AND_UNIT; "
            "use certificate_requests."
        )
    if certificate_requests is None:
        certificate_requests = (_REQUEST,)
    if mode is tls_certificates.Mode.APP:
        return {tls_certificates.Mode.APP: tuple(certificate_requests)}
    return {tls_certificates.Mode.UNIT: tuple(certificate_requests)}


def _resolve_requests(
    certificate_requests: Iterable[CertificateRequest],
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


def _as_csr(raw: str) -> tls_certificates.CertificateSigningRequest:
    """Parse a CSR from a databag entry, so entries compare by content not by whitespace."""
    return tls_certificates.CertificateSigningRequest.from_string(raw)


def _load_provider(databag: dict[str, str]) -> _internal._ProviderApplicationData:
    """Load the provider's application databag, treating unreadable data as empty."""
    try:
        return _internal._ProviderApplicationData.load(databag)
    except tls_certificates.DataValidationError:
        return _internal._ProviderApplicationData()


def _dump_requirer(resolved: Iterable[_ResolvedRequest]) -> dict[str, str]:
    requirer = _internal._RequirerData(
        certificate_signing_requests=[
            _internal._CertificateSigningRequest(
                certificate_signing_request=str(request.csr).strip(),
                ca=request.is_ca,
            )
            for request in resolved
        ]
    )
    ret: dict[str, str] = {}
    requirer.dump(ret)
    return ret


def _certificate_entry(request: _ResolvedRequest) -> _internal._Certificate:
    certificate = _sign(request.csr, age=request.age, is_ca=request.is_ca)
    return _internal._Certificate(
        certificate=str(certificate),
        certificate_signing_request=str(request.csr),
        ca=str(_CA_CERT),
        # leaf to root, the order chain_has_valid_order expects
        chain=[str(certificate), str(_CA_CERT)],
        revoked=True if request.revoked else None,
    )


def _dump_provider(
    resolved: Iterable[_ResolvedRequest],
    capabilities: tls_certificates.ProviderCapabilities | None = None,
) -> dict[str, str]:
    certificates: list[_internal._Certificate] = []
    request_errors: list[_internal._RequestError] = []
    for request in resolved:
        if request.error is not None:
            request_errors.append(
                _internal._RequestError(csr=str(request.csr), error=request.error)
            )
            continue
        certificates.append(_certificate_entry(request))
    provider = _internal._ProviderApplicationData(
        certificates=certificates, request_errors=request_errors, capabilities=capabilities
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


def _relation(endpoint: str, remote_app_name: str, kwargs: _RelationKwargs) -> testing.Relation:
    return testing.Relation(
        endpoint, interface=_INTERFACE_NAME, remote_app_name=remote_app_name, **kwargs
    )
