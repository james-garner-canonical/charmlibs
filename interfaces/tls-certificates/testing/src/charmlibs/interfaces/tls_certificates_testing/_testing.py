# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The stand-in charms: :func:`provider` and :func:`requirer`, and the :class:`Outcome` type."""

from __future__ import annotations

import dataclasses
import datetime
import enum
import json
import logging
import typing

import ops
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from charmlibs.interfaces import tls_certificates

# The library's private module. The renewal threshold the ``renewing`` outcome back-dates
# past lives here, and reusing it is deliberate -- this package and the library are released
# in lockstep and pin each other exactly, so they cannot drift, whereas a copy of the value
# could. Every use is covered by a test.
from charmlibs.interfaces.tls_certificates import _tls_certificates as _internal

from . import _raw
from ._charm_data import CharmData
from ._mocking import mocked

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

logger = logging.getLogger(__name__)

_CA_CERT = tls_certificates.Certificate(raw=_raw.CERT)
_CA_KEY = tls_certificates.PrivateKey(raw=_raw.CA_KEY)
_DEFAULT_KEY = tls_certificates.PrivateKey(raw=_raw.KEY)
_DEFAULT_REQUEST = tls_certificates.CertificateRequestAttributes(common_name="example.com")
_DEFAULT_APP_REQUEST = tls_certificates.CertificateRequestAttributes(common_name="app.example.com")
_DEFAULT_UNIT_REQUEST = tls_certificates.CertificateRequestAttributes(
    common_name="unit.example.com"
)
_DEFAULT_VALIDITY = datetime.timedelta(days=42)
_DEFAULT_DENIAL_MESSAGE = "Denied by the simulated provider."


class _Kind(enum.Enum):
    """Which of the five things the stand-in provider can do with a request. Not public."""

    ISSUED = enum.auto()
    DENIED = enum.auto()
    RENEWING = enum.auto()
    EXPIRED = enum.auto()
    REVOKED = enum.auto()


class Outcome:
    """What the stand-in provider does with each certificate request it sees.

    Passed to :func:`provider` as ``outcome``, either as a single value applying to every
    request, or as a callable choosing one per request::

        tls_certificates_testing.provider(outcome=Outcome.denied())
        tls_certificates_testing.provider(
            outcome=lambda request: (
                Outcome.denied() if request.common_name.startswith("*") else Outcome.issued()
            ),
        )

    The callable receives the ``CertificateRequestAttributes`` the charm asked for,
    reconstructed from the request the charm actually published, so a test can select on
    whatever distinguishes its requests -- usually the common name.

    Built through the classmethods below, never by calling ``Outcome()`` directly.
    """

    def __init__(
        self,
        kind: _Kind,
        *,
        code: tls_certificates.CertificateRequestErrorCode | None = None,
        message: str | None = None,
        reason: str | None = None,
    ) -> None:
        # Not part of the public contract -- instances are built through the classmethods
        # below, which is what keeps a denied outcome's fields meaningless on every other
        # kind rather than merely unused.
        self._kind = kind
        self._code = code
        self._message = message
        self._reason = reason

    @classmethod
    def issued(cls) -> Outcome:
        """A certificate, valid from now. The happy path, and the default."""
        return _ISSUED

    @classmethod
    def denied(
        cls,
        *,
        code: tls_certificates.CertificateRequestErrorCode = (
            tls_certificates.CertificateRequestErrorCode.OTHER
        ),
        message: str = _DEFAULT_DENIAL_MESSAGE,
        reason: str | None = None,
    ) -> Outcome:
        """An error instead of a certificate.

        The requirer library surfaces it through ``get_request_errors()`` and
        ``get_request_error()``, and emits ``certificate_denied``. Customise it with this
        method's own ``code``, ``message`` and ``reason`` arguments.

        Args:
            code: The error code the provider reports.
            message: The message it reports.
            reason: Optional further detail, carried in the error's ``reason`` field.
        """
        return cls(_Kind.DENIED, code=code, message=message, reason=reason)

    @classmethod
    def renewing(cls) -> Outcome:
        """A certificate far enough through its validity period to be due for renewal.

        On its next reconcile the requirer library's renewal safety net withdraws the
        request and replaces it with a fresh one. A real provider answers a fresh request
        with a fresh certificate, so the stand-in applies this outcome only to the *first*
        certificate it issues for each set of request attributes; later answers for the same
        attributes are issued normally, which is what lets the model settle.

        This needs no agreement with the charm's ``renewal_relative_time``: the library caps
        the threshold it derives from that argument, so one back-dating covers every value a
        charm can legally pass.

        Note which of the library's two renewal routes this reaches. When the library stores
        a certificate it schedules a Juju secret expiry, and Juju's ``secret-expired`` drives
        the renewal; separately, a safety net re-checks every certificate on every reconcile,
        for when that event doesn't fire or doesn't complete. This reaches the safety net.
        Both routes withdraw the request and re-request, so the charm ends up in the same
        place; only the event that takes it there differs.
        """
        return _RENEWING

    @classmethod
    def expired(cls) -> Outcome:
        """A certificate whose whole validity period is in the past.

        Use this to test what a charm does when renewal has *failed* and it is left holding
        a dead certificate. The library will not rescue it: the safety net covers
        certificates approaching expiry and stops at expiry itself, so an expired
        certificate stays assigned and is never re-requested. Whether the charm keeps
        serving, goes blocked, or raises the alarm is the charm's own decision, and this is
        how to pin it down.
        """
        return _EXPIRED

    @classmethod
    def revoked(cls) -> Outcome:
        """A certificate published with the relation's ``revoked`` flag set.

        The requirer library removes the certificate's Juju secret on its next reconcile.
        """
        return _REVOKED

    @property
    def code(self) -> tls_certificates.CertificateRequestErrorCode | None:
        """The code the provider reports for a denied outcome.

        ``None`` for every other outcome.
        """
        return self._code

    @property
    def message(self) -> str | None:
        """The message the provider reports for a denied outcome.

        ``None`` for every other outcome.
        """
        return self._message

    @property
    def reason(self) -> str | None:
        """The further detail the provider reports for a denied outcome.

        ``None`` for every other outcome, and for a denied outcome constructed without one.
        """
        return self._reason

    def __repr__(self) -> str:
        if self._kind is not _Kind.DENIED:
            return f"Outcome.{self._kind.name.lower()}()"
        args: list[str] = []
        if (
            code := self._code
        ) is not None and code is not tls_certificates.CertificateRequestErrorCode.OTHER:
            args.append(f"code=CertificateRequestErrorCode.{code.name}")
        if self._message != _DEFAULT_DENIAL_MESSAGE:
            args.append(f"message={self._message!r}")
        if self._reason is not None:
            args.append(f"reason={self._reason!r}")
        return f"Outcome.denied({', '.join(args)})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Outcome):
            return NotImplemented
        return (
            self._kind is other._kind
            and self._code == other._code
            and self._message == other._message
            and self._reason == other._reason
        )

    def __hash__(self) -> int:
        return hash((self._kind, self._code, self._message, self._reason))

    def _denial(self) -> tls_certificates.CertificateError | None:
        """This outcome's ``CertificateError``, or ``None`` if it isn't a denial. Not public.

        ``code`` and ``message`` are only ever ``None`` on a non-denied outcome, because
        :meth:`denied` defaults both, so the checks below narrow rather than validate.
        """
        code, message = self._code, self._message
        if self._kind is not _Kind.DENIED or code is None or message is None:
            return None
        return tls_certificates.CertificateError(
            code=code.value, name=code.name, message=message, reason=self._reason
        )


_ISSUED = Outcome(_Kind.ISSUED)
_RENEWING = Outcome(_Kind.RENEWING)
_EXPIRED = Outcome(_Kind.EXPIRED)
_REVOKED = Outcome(_Kind.REVOKED)


_OutcomeArg: typing.TypeAlias = (
    "Outcome | Callable[[tls_certificates.CertificateRequestAttributes], Outcome]"
)
_Scope: typing.TypeAlias = "typing.Literal[tls_certificates.Mode.APP, tls_certificates.Mode.UNIT]"
_RequestsByMode: typing.TypeAlias = (
    "Mapping[_Scope, Iterable[tls_certificates.CertificateRequestAttributes]]"
)

_PROVIDER_META: Mapping[str, typing.Any] = {
    "name": "tls-certificates-provider",
    "provides": {"certificates": {"interface": "tls-certificates"}},
}
"""The stand-in provider's metadata. One endpoint, so ``Juju.integrate`` resolves it."""

_REQUIRER_META: Mapping[str, typing.Any] = {
    "name": "tls-certificates-requirer",
    "requires": {"certificates": {"interface": "tls-certificates"}},
}
"""The stand-in requirer's metadata. One endpoint, so ``Juju.integrate`` resolves it."""


def provider(
    *,
    outcome: _OutcomeArg = _ISSUED,
    capabilities: tls_certificates.ProviderCapabilities | None = None,
    validity: datetime.timedelta = _DEFAULT_VALIDITY,
    respond: bool = True,
) -> CharmData[ops.CharmBase]:
    """Return a stand-in ``tls-certificates`` provider, for testing a **requirer** charm.

    The charm under test asks for certificates; the stand-in issues them. Because the
    requirer writes first, the certificates are signed from the certificate signing
    requests the charm *actually published* -- never from a canned value. That is what
    makes the stand-in impossible to silently disagree with: there is no request list to
    keep in step with the charm's, and no private key to seed, whether the charm lets the
    library manage its key or supplies its own.

    Deploy it with ``ops.testing.Juju`` and integrate it with the charm under test::

        juju = ops.testing.Juju()
        app = juju.deploy(MyCharm)
        ca = juju.deploy(tls_certificates_testing.provider())
        juju.integrate((app, "certificates"), ca)
        juju.settle()

    The stand-in's endpoint is named ``certificates``; ``Juju.integrate`` resolves it
    unambiguously, since it is the stand-in's only one. The requirer library reads its
    relation with ``Model.get_relation``, which raises when an endpoint carries more than
    one relation, so a requirer charm under test can be integrated with only one provider
    per endpoint. Several *endpoints* are fine, one stand-in each.

    Args:
        outcome: What the provider does with each request -- an :class:`Outcome` from one
            of its constructors, or a callable choosing one per request. Defaults to
            issuing a certificate for everything.
        capabilities: What the provider has advertised about its certificate server.
            ``None``, the default, models a provider that has not advertised anything,
            which ``get_provider_capabilities()`` reports as ``None`` ("not known yet").
            Pass a ``ProviderCapabilities`` -- even an empty one -- to model a provider
            that has, with each field carrying its own three-way meaning per the library's
            docs.
        validity: How long issued certificates are valid for. Rarely worth changing:
            ``Outcome.renewing()`` and ``Outcome.expired()`` express the interesting
            positions within the validity period without needing a specific length.
        respond: Whether the stand-in answers at all. ``respond=False`` joins the relation
            and writes nothing, so a test can assert on how the charm behaves while it
            waits for its certificates.

    Returns:
        A ``CharmData`` describing the stand-in charm, for ``Juju.deploy``.
    """
    options = _ProviderOptions(
        outcome=outcome, capabilities=capabilities, validity=validity, respond=respond
    )
    charm_type = type("_ProviderCharm", (_ProviderCharm,), {"_options": options})
    return CharmData(charm_type, meta=_PROVIDER_META, mocking=mocked)


def requirer(
    *,
    certificate_requests: Iterable[tls_certificates.CertificateRequestAttributes] | None = None,
    mode: tls_certificates.Mode = tls_certificates.Mode.UNIT,
    certificate_requests_by_mode: _RequestsByMode | None = None,
    private_key: tls_certificates.PrivateKey = _DEFAULT_KEY,
    respond: bool = True,
) -> CharmData[ops.CharmBase]:
    """Return a stand-in ``tls-certificates`` requirer, for testing a **provider** charm.

    The charm under test issues certificates; the stand-in asks for them. Here the stand-in
    writes first, so there is nothing to derive from the charm and the requests are supplied
    as ordinary fixture configuration::

        juju = ops.testing.Juju()
        app = juju.deploy(MyCharm)
        workload = juju.deploy(tls_certificates_testing.requirer())
        juju.integrate((app, "certificates"), workload)
        juju.settle()

    The stand-in's endpoint is named ``certificates``. A provider charm may be related to
    several requirer applications on one endpoint, so several stand-ins on one endpoint are
    supported -- deploy one per application, with distinct application names.

    Args:
        certificate_requests: The requests the stand-in makes. Defaults to one request for
            ``example.com``. A request with ``is_ca=True`` asks for a CA certificate. Must
            not be given when ``mode`` is ``Mode.APP_AND_UNIT``.
        mode: Which databag the requests go in, mirroring the ``mode`` a real requirer
            would pass to ``TLSCertificatesRequiresV4``. ``Mode.UNIT`` (the default) uses
            the stand-in's unit databags, ``Mode.APP`` its application databag, and
            ``Mode.APP_AND_UNIT`` splits them per ``certificate_requests_by_mode``.
        certificate_requests_by_mode: The requests per scope, mirroring
            ``TLSCertificatesRequiresV4(certificate_requests_by_mode=...)``. Required when
            ``mode`` is ``Mode.APP_AND_UNIT`` -- where it defaults to one application and
            one unit request -- and rejected otherwise.
        private_key: The key the stand-in signs its requests with. Free to choose; a
            provider charm never sees it, and ``TLSCertificatesProvidesV4`` manages no key
            of its own, so nothing needs seeding for the charm under test.
        respond: Whether the stand-in publishes its requests at all. ``respond=False``
            joins the relation and writes nothing, so a test can assert on how the charm
            behaves with a silent requirer.

    Returns:
        A ``CharmData`` describing the stand-in charm, for ``Juju.deploy``.

    Raises:
        ValueError: If ``certificate_requests`` and ``certificate_requests_by_mode`` aren't
            used in the combination ``mode`` requires. Mirrors the pairing rules the library
            enforces on a real requirer's own arguments, so a stand-in can't be built in a
            shape a real requirer could not have produced.
    """
    options = _RequirerOptions(
        certificate_requests=certificate_requests,
        mode=mode,
        certificate_requests_by_mode=certificate_requests_by_mode,
        private_key=private_key,
        respond=respond,
    )
    charm_type = type("_RequirerCharm", (_RequirerCharm,), {"_options": options})
    return CharmData(charm_type, meta=_REQUIRER_META, mocking=mocked)


# ---------------------------------------------------------------------- the stand-in charms


@dataclasses.dataclass(frozen=True)
class _ProviderOptions:
    """The validated arguments of one ``provider()`` call. Not public."""

    outcome: _OutcomeArg
    capabilities: tls_certificates.ProviderCapabilities | None
    validity: datetime.timedelta
    respond: bool


class _ProviderCharm(ops.CharmBase):
    """The stand-in provider charm. Not public; bound to its arguments by ``provider()``.

    Reads and writes through the library's public provider API, except for the ``revoked``
    flag, which the public API can only set on every certificate at once. The library
    already removes certificates whose request has gone, so the stand-in derives and
    reconciles without any code of its own for either. Only the leader writes the
    application databag, which is the only databag this side of the interface uses.
    """

    _options: typing.ClassVar[_ProviderOptions]
    _stored = ops.StoredState()

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self._stored.set_default(renewed=[])
        self.certificates = tls_certificates.TLSCertificatesProvidesV4(
            self, "certificates", provider_capabilities=self._options.capabilities
        )
        if self._options.respond:
            framework.observe(self.on["certificates"].relation_changed, self._reconcile)

    def _reconcile(self, _: ops.EventBase) -> None:
        if not self.unit.is_leader():
            return
        for request in self.certificates.get_outstanding_certificate_requests():
            if self._already_revoked(request):
                # Revoked certificates don't count as issued, so the request stays
                # outstanding. Answering it again would never settle.
                continue
            outcome = self._outcome_for(request)
            if (denial := outcome._denial()) is not None:
                self.certificates.set_relation_error(
                    tls_certificates.ProviderCertificateError(
                        relation_id=request.relation_id,
                        certificate_signing_request=request.certificate_signing_request,
                        error=denial,
                    )
                )
                continue
            certificate = request.certificate_signing_request.sign(
                ca=_CA_CERT,
                ca_private_key=_CA_KEY,
                validity=self._options.validity,
                is_ca=request.is_ca,
            )
            if outcome == Outcome.renewing() and self._first_renewal_for(request):
                # See _first_renewal_for for why renewing applies only once.
                age = (_internal._MAX_RENEWAL_FRACTION + 1.0) / 2
                certificate = _backdate(certificate, age=age, validity=self._options.validity)
            elif outcome == Outcome.expired():
                certificate = _backdate(certificate, age=1.5, validity=self._options.validity)
            self.certificates.set_relation_certificate(
                tls_certificates.ProviderCertificate(
                    relation_id=request.relation_id,
                    certificate=certificate,
                    certificate_signing_request=request.certificate_signing_request,
                    ca=_CA_CERT,
                    chain=[certificate, _CA_CERT],  # leaf to root
                )
            )
            if outcome == Outcome.revoked():
                self._revoke(request)

    def _already_revoked(self, request: tls_certificates.RequirerCertificateRequest) -> bool:
        return any(
            issued.revoked
            and issued.certificate_signing_request == request.certificate_signing_request
            for issued in self.certificates.get_provider_certificates(request.relation_id)
        )

    def _revoke(self, request: tls_certificates.RequirerCertificateRequest) -> None:
        """Set the ``revoked`` flag on the certificate just issued for ``request``.

        ``set_relation_certificate`` doesn't write the flag, and ``revoke_all_certificates``
        can't revoke one certificate among several, so this goes through the library's
        internals. The testing package is released in lockstep with the library, so they
        can't drift.
        """
        relation = self.model.get_relation("certificates", request.relation_id)
        assert relation is not None  # the request came from this relation
        entries = self.certificates._load_provider_certificates(relation)
        csr = str(request.certificate_signing_request)
        for entry in entries:
            if entry.certificate_signing_request == csr:
                entry.revoked = True
        self.certificates._dump_provider_certificates(relation, entries)

    def _outcome_for(self, request: tls_certificates.RequirerCertificateRequest) -> Outcome:
        if isinstance(self._options.outcome, Outcome):
            return self._options.outcome
        # Reconstruct what the charm asked for, so the callable selects on the request
        # rather than on the wire format.
        attributes = tls_certificates.CertificateRequestAttributes.from_csr(
            request.certificate_signing_request, is_ca=request.is_ca
        )
        outcome = self._options.outcome(attributes)
        if not isinstance(outcome, Outcome):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(
                f"The outcome callable returned {outcome!r}, not a "
                "tls_certificates_testing.Outcome."
            )
        return outcome

    def _first_renewal_for(self, request: tls_certificates.RequirerCertificateRequest) -> bool:
        """Whether this is the first renewing certificate issued for these attributes.

        ``Outcome.renewing()`` makes the requirer withdraw its request and re-request, so a
        stand-in that answered every request that way would never settle. A real provider
        answers a fresh request with a fresh certificate, so ``renewing`` applies only to
        the first certificate issued for each set of request attributes, per relation;
        later answers for the same attributes are issued normally.

        The record is kept in stored state, which is part of the model. The relation data
        can't serve: once the requirer withdraws the request, the library removes the
        certificate that answered it, and the re-request would look like a first request.
        The key is the request's attributes rather than the signing request, because a
        re-request has a new signing request (a new unique identifier, and a new key if the
        charm has rotated) for the same attributes.
        """
        attributes = tls_certificates.CertificateRequestAttributes.from_csr(
            request.certificate_signing_request, is_ca=request.is_ca
        )
        key = f"{request.relation_id}:{_attributes_key(attributes)}"
        renewed = typing.cast("list[str]", self._stored.renewed)
        if key in renewed:
            return False
        self._stored.renewed = [*renewed, key]
        return True


@dataclasses.dataclass(frozen=True, init=False)
class _RequirerOptions:
    """The validated arguments of one ``requirer()`` call. Not public."""

    scopes: Mapping[_Scope, tuple[tls_certificates.CertificateRequestAttributes, ...]]
    mode: tls_certificates.Mode
    private_key: tls_certificates.PrivateKey
    respond: bool

    def __init__(
        self,
        *,
        certificate_requests: (
            Iterable[tls_certificates.CertificateRequestAttributes] | None
        ) = None,
        mode: tls_certificates.Mode = tls_certificates.Mode.UNIT,
        certificate_requests_by_mode: _RequestsByMode | None = None,
        private_key: tls_certificates.PrivateKey = _DEFAULT_KEY,
        respond: bool = True,
    ) -> None:
        # The iterables are consumed into tuples straight away, so that a stand-in really
        # is reusable: a generator would otherwise be consumed by the first deployment and
        # empty for the second.
        scopes = _requests_by_mode(mode, certificate_requests, certificate_requests_by_mode)
        object.__setattr__(self, "scopes", scopes)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "private_key", private_key)
        object.__setattr__(self, "respond", respond)


class _RequirerCharm(ops.CharmBase):
    """The stand-in requirer charm. Not public; bound to its arguments by ``requirer()``.

    Constructs ``TLSCertificatesRequiresV4`` with the requests it was given, and the
    library does the publishing -- the requests reach the relation in the right databags,
    signed with the stand-in's key, exactly as a real requirer's would.
    """

    _options: typing.ClassVar[_RequirerOptions]

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        if not self._options.respond:
            # Join the relation and write nothing: no library object, no observers.
            return
        kwargs: dict[str, typing.Any] = {"private_key": self._options.private_key}
        if self._options.mode is tls_certificates.Mode.APP_AND_UNIT:
            kwargs["certificate_requests_by_mode"] = dict(self._options.scopes)
        else:
            (requests,) = self._options.scopes.values()
            kwargs["certificate_requests"] = list(requests)
        self.certificates = tls_certificates.TLSCertificatesRequiresV4(
            charm=self,
            relationship_name="certificates",
            mode=self._options.mode,
            **kwargs,
        )


def _requests_by_mode(
    mode: tls_certificates.Mode,
    certificate_requests: Iterable[tls_certificates.CertificateRequestAttributes] | None,
    certificate_requests_by_mode: _RequestsByMode | None,
) -> dict[_Scope, tuple[tls_certificates.CertificateRequestAttributes, ...]]:
    """Validate the request arguments against ``mode`` and return them keyed by scope."""
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
                tls_certificates.Mode.APP: (_DEFAULT_APP_REQUEST,),
                tls_certificates.Mode.UNIT: (_DEFAULT_UNIT_REQUEST,),
            }
        # Iterate as plain Modes: the annotation rules APP_AND_UNIT out, but a caller
        # without a type checker can still pass it, and it must not reach the databag.
        keys = typing.cast("Iterable[tls_certificates.Mode]", certificate_requests_by_mode)
        invalid = sorted(m.name for m in keys if m is app_and_unit)
        if invalid:
            raise ValueError(
                "certificate_requests_by_mode keys must be Mode.APP or Mode.UNIT, "
                f"not {', '.join(invalid)}."
            )
        return {scope: tuple(requests) for scope, requests in certificate_requests_by_mode.items()}
    if certificate_requests_by_mode is not None:
        raise ValueError(
            "certificate_requests_by_mode is only valid when mode is Mode.APP_AND_UNIT; "
            "use certificate_requests."
        )
    if certificate_requests is None:
        certificate_requests = (_DEFAULT_REQUEST,)
    if mode is tls_certificates.Mode.APP:
        return {tls_certificates.Mode.APP: tuple(certificate_requests)}
    if mode is tls_certificates.Mode.UNIT:
        return {tls_certificates.Mode.UNIT: tuple(certificate_requests)}
    raise ValueError(f"mode must be Mode.UNIT, Mode.APP or Mode.APP_AND_UNIT, not {mode!r}.")


def _attributes_key(attributes: tls_certificates.CertificateRequestAttributes) -> str:
    """A stable string for ``attributes``, for stored state. Equal attributes, equal keys."""
    return json.dumps(
        {
            "common_name": attributes.common_name,
            "sans_dns": sorted(attributes.sans_dns or ()),
            "sans_ip": sorted(attributes.sans_ip or ()),
            "sans_oid": sorted(attributes.sans_oid or ()),
            "email_address": attributes.email_address,
            "organization": attributes.organization,
            "organizational_unit": attributes.organizational_unit,
            "country_name": attributes.country_name,
            "state_or_province_name": attributes.state_or_province_name,
            "locality_name": attributes.locality_name,
            "is_ca": attributes.is_ca,
        },
        sort_keys=True,
    )


def _backdate(
    certificate: tls_certificates.Certificate,
    age: float,
    validity: datetime.timedelta,
) -> tls_certificates.Certificate:
    """Re-issue ``certificate`` with ``age`` of its validity period already elapsed.

    The library computes renewal as a fraction of ``expiry_time - validity_start_time``, and
    signing hardcodes ``not_valid_before`` to the time of issue, so aged certificates can
    only be built by hand: sign through the library as usual, keeping its extension
    handling, then rebuild the result with shifted validity dates and everything else copied
    verbatim, re-signed by the same testing CA.
    """
    cert = x509.load_pem_x509_certificate(str(certificate).encode())
    not_valid_before = datetime.datetime.now(datetime.timezone.utc) - validity * age
    builder = x509.CertificateBuilder(
        subject_name=cert.subject,
        issuer_name=cert.issuer,
        public_key=cert.public_key(),
        serial_number=cert.serial_number,
        not_valid_before=not_valid_before,
        not_valid_after=not_valid_before + validity,
    )
    for extension in cert.extensions:
        builder = builder.add_extension(extension.value, extension.critical)
    ca_key = serialization.load_pem_private_key(str(_CA_KEY).encode(), password=None)
    assert isinstance(ca_key, rsa.RSAPrivateKey)  # the testing CA is RSA
    backdated = builder.sign(ca_key, hashes.SHA256())
    return tls_certificates.Certificate.from_string(
        backdated.public_bytes(serialization.Encoding.PEM).decode()
    )
