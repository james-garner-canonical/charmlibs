# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The stand-in charms: :func:`provider` and :func:`requirer`."""

from __future__ import annotations

import dataclasses
import typing

import ops

from charmlibs.interfaces import certificate_transfer

# The library's private module, for its databag models. Writing the v0 wire format means
# writing the interface's wire format, which is private. Reusing it is deliberate -- this
# package and the library are released in lockstep and pin each other exactly, so they
# cannot drift, whereas a second copy of the wire format could. Every use is covered by a
# test.
from charmlibs.interfaces.certificate_transfer import _certificate_transfer as _internal

from . import _raw
from ._charm_data import CharmData
from ._mocking import mocked

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

_INTERFACE_NAME = 'certificate_transfer'

_DEFAULT_CERTIFICATES: tuple[str, ...] = (_raw.CA_CERTS[0],)
"""What a provider transfers unless the test says otherwise: one CA certificate."""

_Version: typing.TypeAlias = 'typing.Literal[0, 1]'

_V0: _Version = 0
_V1: _Version = 1
_VERSIONS = (_V0, _V1)
"""The two versions of this interface's wire format."""

_PROVIDER_META: Mapping[str, typing.Any] = {
    'name': 'certificate-transfer-provider',
    'provides': {'certificates': {'interface': _INTERFACE_NAME}},
}
"""The stand-in provider's metadata. One endpoint, so ``Juju.integrate`` resolves it."""

_REQUIRER_META: Mapping[str, typing.Any] = {
    'name': 'certificate-transfer-requirer',
    'requires': {'certificates': {'interface': _INTERFACE_NAME}},
}
"""The stand-in requirer's metadata. One endpoint, so ``Juju.integrate`` resolves it."""


def provider(
    *,
    certificates: Iterable[str] | None = None,
    interface_version: _Version | None = None,
    respond: bool = True,
) -> CharmData[ops.CharmBase]:
    """Return a stand-in ``certificate_transfer`` provider, for testing a **requirer** charm.

    The charm under test receives CA certificates; the stand-in hands them over. The
    certificates themselves are the stand-in's to choose, because the requirer asks for
    nothing in particular -- but *which version of the wire format they are written in* is
    derived from what the charm published, because that is the one thing the requirer does
    say, and because it is what the real provider library decides from.

    Deploy it with ``ops.testing.Juju`` and integrate it with the charm under test::

        juju = ops.testing.Juju()
        app = juju.deploy(MyCharm)
        ca = juju.deploy(certificate_transfer_testing.provider())
        juju.integrate((app, 'certificates'), ca)
        juju.settle()

    The stand-in's endpoint is named ``certificates``; ``Juju.integrate`` resolves it
    unambiguously, since it is the stand-in's only one. A requirer charm aggregates the
    certificates from every relation on the endpoint, so several stand-ins on one endpoint
    are supported -- deploy one per application, with distinct application names.

    Args:
        certificates: The CA certificates this provider transfers, as PEM strings. Defaults
            to a single self-signed CA certificate, generated once and shipped with this
            package, valid for a hundred years so that a test never starts failing on a
            date. The interface treats these as opaque, so anything a charm under test can
            make sense of will do, including a deliberately malformed string. Pass an empty
            collection to model a provider that has nothing to transfer yet: in the v1
            format that is an answer, and it is an empty one; in v0 it is nothing at all,
            because v0 has no way to say "none".
        interface_version: Which version of the wire format to answer in. ``None``, the
            default, decides the way the real provider library does: v1 if the charm under
            test advertised ``version: 1``, and v0 otherwise. Pass ``1`` or ``0`` to force
            it -- ``0`` being how a test models an old provider charm talking to a modern
            requirer, which is the case the library's v0 fallback exists for and which
            cannot otherwise be reached from a leader charm.
        respond: Whether the stand-in answers at all. ``respond=False`` joins the relation
            and writes nothing, so a test can assert on how the charm behaves while it
            waits for its certificates.

    Returns:
        A ``CharmData`` describing the stand-in charm, for ``Juju.deploy``.

    Raises:
        ValueError: If ``interface_version`` is neither ``None``, ``0`` nor ``1``.
    """
    options = _ProviderOptions(
        certificates=certificates, interface_version=interface_version, respond=respond
    )
    charm_type = type('_ProviderCharm', (_ProviderCharm,), {'_options': options})
    return CharmData(charm_type, meta=_PROVIDER_META, mocking=mocked)


def requirer(
    *,
    interface_version: _Version = _V1,
    respond: bool = True,
) -> CharmData[ops.CharmBase]:
    """Return a stand-in ``certificate_transfer`` requirer, for testing a **provider** charm.

    The charm under test hands over CA certificates; the stand-in receives them. A requirer
    says only one thing on this interface -- the version of the wire format it understands
    -- and it says it first, so there is nothing to derive from the charm and the request
    is ordinary fixture configuration::

        juju = ops.testing.Juju()
        app = juju.deploy(MyCharm)
        client = juju.deploy(certificate_transfer_testing.requirer())
        juju.integrate((app, 'send-ca-cert'), client)
        juju.settle()

    The stand-in's endpoint is named ``certificates``. A provider charm transfers to every
    relation on the endpoint, so several stand-ins on one endpoint are supported -- deploy
    one per application, with distinct application names.

    Args:
        interface_version: The version of the wire format this requirer advertises.
            ``1``, the default, is what ``CertificateTransferRequires`` writes. Pass ``0``
            to model an old requirer charm, which advertises nothing at all and so is
            answered in the v0 format.
        respond: Whether the stand-in publishes its version at all. ``respond=False``
            joins the relation and writes nothing, so a test can assert on how the charm
            behaves with a silent requirer -- which the provider library reads exactly as
            it reads a v0 requirer, since an absent ``version`` key is how v0 is spelled.

    Returns:
        A ``CharmData`` describing the stand-in charm, for ``Juju.deploy``.

    Raises:
        ValueError: If ``interface_version`` is neither ``0`` nor ``1``.
    """
    options = _RequirerOptions(interface_version=interface_version, respond=respond)
    charm_type = type('_RequirerCharm', (_RequirerCharm,), {'_options': options})
    return CharmData(charm_type, meta=_REQUIRER_META, mocking=mocked)


# ---------------------------------------------------------------------- the stand-in charms


@dataclasses.dataclass(frozen=True, init=False)
class _ProviderOptions:
    """The validated arguments of one ``provider()`` call. Not public."""

    certificates: tuple[str, ...]
    interface_version: _Version | None
    respond: bool

    def __init__(
        self,
        *,
        certificates: Iterable[str] | None = None,
        interface_version: _Version | None = None,
        respond: bool = True,
    ) -> None:
        # The iterable is consumed into a tuple straight away, so that a stand-in really is
        # reusable: a generator would otherwise be consumed by the first deployment and
        # empty for the second.
        certs = _DEFAULT_CERTIFICATES if certificates is None else tuple(certificates)
        _check_version(interface_version, allow_none=True)
        object.__setattr__(self, 'certificates', certs)
        object.__setattr__(self, 'interface_version', interface_version)
        object.__setattr__(self, 'respond', respond)


class _ProviderCharm(ops.CharmBase):
    """The stand-in provider charm. Not public; bound to its arguments by ``provider()``.

    ``certificate_transfer`` is a one-way interface: the provider hands CA certificates to
    the requirer, which reads them and answers nothing. So the provider writes first, and
    there is nothing to derive the *certificates* from -- they come from the stand-in's
    arguments. What is derived is the *format* they are written in, from the version the
    charm under test advertised, exactly as the real provider library decides it.

    Reconcile here means keeping the transferred set equal to the stand-in's
    ``certificates`` argument, in the format the requirer's advertised version calls for:
    a certificate the stand-in no longer transfers is removed from the wire, and a change
    in the advertised version rewrites the answer in the other format, clearing the old
    one. The library's ``add_certificates`` only ever adds, so the removal half is done
    through the library's private databag models -- allowed because this package and the
    library are versioned in lockstep. Only the leader writes, which is the only unit that
    can write either databag this side of the interface uses.
    """

    _options: typing.ClassVar[_ProviderOptions]

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.ct = certificate_transfer.CertificateTransferProvides(self, 'certificates')
        if self._options.respond:
            framework.observe(self.on['certificates'].relation_created, self._reconcile)
            framework.observe(self.on['certificates'].relation_joined, self._reconcile)
            framework.observe(self.on['certificates'].relation_changed, self._reconcile)

    def _reconcile(self, _: ops.EventBase) -> None:
        if not self.unit.is_leader():
            # Transferring is leader-only; the library warns and does nothing otherwise.
            return
        for relation in self.model.relations['certificates']:
            if not relation.active:
                continue
            self._reconcile_relation(relation)

    def _reconcile_relation(self, relation: ops.Relation) -> None:
        """Make this relation's databags exactly the stand-in's answer, in the right format."""
        version = self._version_for(relation)
        wanted = set(self._options.certificates)
        if version == _V1:
            # add_certificates only ever adds, so what the stand-in no longer transfers is
            # removed through the library's private databag model (lockstep versioning).
            databag = relation.data[self.model.app]
            existing = _internal.ProviderApplicationData().load(databag).certificates
            if existing != wanted:
                _internal.ProviderApplicationData(certificates=existing & wanted).dump(
                    databag, True
                )
            self.ct.add_certificates(wanted, relation_id=relation.id)
            # Switching formats clears the other one: the state must never hold both
            # halves of the conversation at once.
            unit_databag = relation.data[self.model.unit]
            for key in ('ca', 'certificate', 'chain', 'version'):
                unit_databag.pop(key, None)
        else:
            # v0 has no way to say "no certificates" -- `ca` and `certificate` are single
            # required strings -- so the real library writes nothing at all in that case.
            unit_databag = relation.data[self.model.unit]
            if wanted:
                chain = sorted(wanted)
                # The real library picks `list(data)[0]` out of a set for both `ca` and
                # `certificate`, which is to say an arbitrary one. Sorted, so it's the same
                # one every run; the requirer reads `chain` and ignores the other two.
                _internal.ProviderUnitDataV0(ca=chain[0], certificate=chain[0], chain=chain).dump(
                    unit_databag, True
                )
            else:
                for key in ('ca', 'certificate', 'chain', 'version'):
                    unit_databag.pop(key, None)
            # Clear the v1 half, as above.
            relation.data[self.model.app].pop('certificates', None)
            relation.data[self.model.app].pop('version', None)

    def _version_for(self, relation: ops.Relation) -> _Version:
        """The wire format to answer in: forced, or derived from what the charm published."""
        if self._options.interface_version is not None:
            return self._options.interface_version
        # CertificateTransferProvides._set_relation_data reads the requirer's application
        # databag exactly like this, defaulting to v0 where the key is absent. Note that
        # the value is the raw databag string rather than the parsed model: the requirer
        # writes it with json.dumps, so v1 is the two characters `"1"` minus the quotes.
        if relation.data.get(relation.app, {}).get('version', '0') == '1':
            return _V1
        return _V0


@dataclasses.dataclass(frozen=True, init=False)
class _RequirerOptions:
    """The validated arguments of one ``requirer()`` call. Not public."""

    interface_version: _Version
    respond: bool

    def __init__(
        self,
        *,
        interface_version: _Version = _V1,
        respond: bool = True,
    ) -> None:
        _check_version(interface_version, allow_none=False)
        object.__setattr__(self, 'interface_version', interface_version)
        object.__setattr__(self, 'respond', respond)


class _RequirerCharm(ops.CharmBase):
    """The stand-in requirer charm. Not public; bound to its arguments by ``requirer()``.

    Constructs ``CertificateTransferRequires`` and lets the library do the publishing: it
    writes ``version: 1`` to the application databag on ``relation-created``, from the
    leader unit only, exactly as a real requirer's library does. A v0 requirer advertises
    nothing -- an absent ``version`` key *is* how v0 is spelled -- so for one the library
    object is never constructed and nothing is written.
    """

    _options: typing.ClassVar[_RequirerOptions]

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        if not self._options.respond or self._options.interface_version == _V0:
            # Join the relation and write nothing: no library object, no observers.
            return
        self.ct = certificate_transfer.CertificateTransferRequires(self, 'certificates')


def _check_version(version: object, *, allow_none: bool) -> None:
    """Raise early where interface_version isn't a version of this interface."""
    if version in _VERSIONS or (version is None and allow_none):
        return
    allowed = 'None, 0 or 1' if allow_none else '0 or 1'
    raise ValueError(
        f'interface_version={version!r} is not a version of the certificate_transfer '
        f'interface. Pass {allowed}.'
    )
