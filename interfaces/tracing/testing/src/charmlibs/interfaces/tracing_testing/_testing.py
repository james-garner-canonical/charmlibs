# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The stand-in charms: :func:`provider` and :func:`requirer`."""

from __future__ import annotations

import dataclasses
import typing

import ops

from charmlibs.interfaces import tracing

from ._charm_data import CharmData
from ._mocking import mocked

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

_PORTS: dict[tracing.ReceiverProtocol, int] = {
    'jaeger_grpc': 14250,
    'jaeger_thrift_http': 14268,
    'otlp_grpc': 4317,
    'otlp_http': 4318,
    'zipkin': 9411,
}
"""The port the stand-in provider serves each protocol on: each protocol's usual one."""

_DEFAULT_HOST = 'tracing.example.com'
_DEFAULT_PROTOCOLS: tuple[tracing.ReceiverProtocol, ...] = ('otlp_http',)

_PROVIDER_META: Mapping[str, typing.Any] = {
    'name': 'tracing-provider',
    'provides': {'tracing': {'interface': 'tracing'}},
}
"""The stand-in provider's metadata. One endpoint, so ``Juju.integrate`` resolves it."""

_REQUIRER_META: Mapping[str, typing.Any] = {
    'name': 'tracing-requirer',
    'requires': {'tracing': {'interface': 'tracing'}},
}
"""The stand-in requirer's metadata. One endpoint, so ``Juju.integrate`` resolves it."""


def provider(
    *,
    supported_protocols: Iterable[tracing.ReceiverProtocol] | None = None,
    host: str = _DEFAULT_HOST,
    tls: bool = False,
    respond: bool = True,
) -> CharmData[ops.CharmBase]:
    """Return a stand-in ``tracing`` provider, for testing a **requirer** charm.

    The charm under test asks for protocols to send traces with; the stand-in answers with
    a URL for each one it supports. Because the requirer writes first, the receivers are
    derived from the protocols the charm *actually requested* -- never from a canned list.
    That is what makes the stand-in impossible to silently disagree with: there is no list
    of protocols to keep in step with the charm's own.

    Deploy it with ``ops.testing.Juju`` and integrate it with the charm under test::

        juju = ops.testing.Juju()
        app = juju.deploy(MyCharm)
        tempo = juju.deploy(tracing_testing.provider())
        juju.integrate((app, 'tracing'), tempo)
        juju.settle()

    The stand-in's endpoint is named ``tracing``; ``Juju.integrate`` resolves it
    unambiguously, since it is the stand-in's only one. A requirer charm may be related to
    several tracing providers on one endpoint, if its metadata doesn't set ``limit: 1`` --
    deploy one stand-in per application, with distinct application names.

    Args:
        supported_protocols: The protocols this provider serves. ``None``, the default,
            means it serves every protocol the charm requests, which is the happy path.
            Pass a subset to model a provider that doesn't support everything asked of it
            -- it answers with the protocols it has, omitting the rest, exactly as a real
            provider does. Pass an empty collection to model one that supports none of
            them, which still publishes an answer, just an empty one.
        host: The host the receiver URLs point at. Each protocol is served on its usual
            port: 4317 for ``otlp_grpc``, 4318 for ``otlp_http``, 9411 for ``zipkin``,
            14250 for ``jaeger_grpc`` and 14268 for ``jaeger_thrift_http``.
        tls: Whether the provider is behind TLS, making the URLs of the HTTP protocols
            ``https://`` rather than ``http://``. gRPC URLs carry no scheme either way, as
            the interface requires, so this is invisible to a charm that requests only gRPC
            protocols.
        respond: Whether the stand-in answers at all. ``respond=False`` joins the relation
            and writes nothing, so a test can assert on how the charm behaves while it
            waits for its endpoints.

    Returns:
        A ``CharmData`` describing the stand-in charm, for ``Juju.deploy``.

    Raises:
        ValueError: If ``supported_protocols`` names something that isn't a protocol of
            this interface.
    """
    options = _ProviderOptions(
        supported_protocols=supported_protocols, host=host, tls=tls, respond=respond
    )
    charm_type = type('_ProviderCharm', (_ProviderCharm,), {'_options': options})
    return CharmData(charm_type, meta=_PROVIDER_META, mocking=mocked)


def requirer(
    *,
    protocols: Sequence[tracing.ReceiverProtocol] = _DEFAULT_PROTOCOLS,
    respond: bool = True,
) -> CharmData[ops.CharmBase]:
    """Return a stand-in ``tracing`` requirer, for testing a **provider** charm.

    The charm under test serves tracing endpoints; the stand-in asks for them. Here the
    stand-in writes first, so there is nothing to derive from the charm and the request is
    supplied as ordinary fixture configuration::

        juju = ops.testing.Juju()
        app = juju.deploy(MyCharm)
        workload = juju.deploy(tracing_testing.requirer())
        juju.integrate((app, 'tracing'), workload)
        juju.settle()

    The stand-in's endpoint is named ``tracing``. A provider charm aggregates the protocols
    requested across every relation on the endpoint, so several stand-ins on one endpoint
    are supported -- deploy one per application, with distinct application names.

    Args:
        protocols: The protocols this requirer asks to send traces with. Defaults to
            ``otlp_http`` alone.
        respond: Whether the stand-in publishes its request at all. ``respond=False``
            joins the relation and writes nothing, so a test can assert on how the charm
            behaves with a silent requirer.

    Returns:
        A ``CharmData`` describing the stand-in charm, for ``Juju.deploy``.

    Raises:
        ValueError: If ``protocols`` is empty, or names something that isn't a protocol of
            this interface. The library refuses an empty request too: a requirer that wants
            nothing doesn't write, which is what ``respond=False`` is for.
    """
    options = _RequirerOptions(protocols=protocols, respond=respond)
    charm_type = type('_RequirerCharm', (_RequirerCharm,), {'_options': options})
    return CharmData(charm_type, meta=_REQUIRER_META, mocking=mocked)


# ---------------------------------------------------------------------- the stand-in charms


@dataclasses.dataclass(frozen=True, init=False)
class _ProviderOptions:
    """The validated arguments of one ``provider()`` call. Not public."""

    supported_protocols: tuple[tracing.ReceiverProtocol, ...] | None
    host: str
    tls: bool
    respond: bool

    def __init__(
        self,
        *,
        supported_protocols: Iterable[tracing.ReceiverProtocol] | None = None,
        host: str = _DEFAULT_HOST,
        tls: bool = False,
        respond: bool = True,
    ) -> None:
        # The iterable is consumed into a tuple straight away, so that a stand-in really is
        # reusable: a generator would otherwise be consumed by the first deployment and
        # empty for the second.
        protocols = None if supported_protocols is None else tuple(supported_protocols)
        if protocols is not None:
            _check_protocols(protocols, 'supported_protocols')
        object.__setattr__(self, 'supported_protocols', protocols)
        object.__setattr__(self, 'host', host)
        object.__setattr__(self, 'tls', tls)
        object.__setattr__(self, 'respond', respond)


class _ProviderCharm(ops.CharmBase):
    """The stand-in provider charm. Not public; bound to its arguments by ``provider()``.

    Reads the charm under test's request through the library's public provider API, and
    answers through ``publish_receivers`` -- which recomputes the application databag from
    the receivers it is given, so a protocol the charm has stopped asking for disappears
    from the answer on the next reconcile, exactly as with a real provider. Only the leader
    writes the application databag, which is the only databag this side of the interface
    uses.

    The library answers every relation with the same receivers, for the union of what all
    related applications requested, so a stand-in integrated with several charms gives each
    of them the same answer. That is the library's behaviour for a real provider too, so the
    stand-in reproduces it rather than answering each relation separately.
    """

    _options: typing.ClassVar[_ProviderOptions]

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.tracing = tracing.TracingEndpointProvider(self)
        if self._options.respond:
            framework.observe(self.tracing.on.request, self._reconcile)

    def _reconcile(self, _: ops.EventBase) -> None:
        if not self.unit.is_leader():
            # Publishing is leader-only; the library raises otherwise.
            return
        # requested_protocols is unannotated, and everything it can hold is a protocol.
        requested = typing.cast(
            'Iterable[tracing.ReceiverProtocol]', self.tracing.requested_protocols()
        )
        self.tracing.publish_receivers([
            (protocol, self._url(protocol))
            for protocol in sorted(requested)
            if self._serves(protocol)
        ])

    def _serves(self, protocol: str) -> bool:
        """Whether this provider answers a requested protocol with a receiver."""
        if protocol not in _PORTS:
            # A protocol the interface doesn't define. A real provider can only omit it, so
            # that is what this does -- the requirer's own library logs the resulting
            # absence when the charm asks for the endpoint.
            return False
        if self._options.supported_protocols is None:
            return True
        return protocol in self._options.supported_protocols

    def _url(self, protocol: tracing.ReceiverProtocol) -> str:
        """The URL for one protocol: no scheme for gRPC, as the interface requires."""
        port = _PORTS[protocol]
        transport = tracing.receiver_protocol_to_transport_protocol[protocol]
        if transport is tracing.TransportProtocolType.grpc:
            return f'{self._options.host}:{port}'
        return f'{"https" if self._options.tls else "http"}://{self._options.host}:{port}'


@dataclasses.dataclass(frozen=True, init=False)
class _RequirerOptions:
    """The validated arguments of one ``requirer()`` call. Not public."""

    protocols: tuple[tracing.ReceiverProtocol, ...]
    respond: bool

    def __init__(
        self,
        *,
        protocols: Sequence[tracing.ReceiverProtocol] = _DEFAULT_PROTOCOLS,
        respond: bool = True,
    ) -> None:
        # Consumed into a tuple straight away, as for _ProviderOptions.
        requested = tuple(protocols)
        if not requested:
            raise ValueError(
                'requirer() needs at least one protocol to request. '
                'TracingEndpointRequirer.request_protocols rejects an empty sequence too. '
                'A stand-in that asks for nothing is requirer(respond=False).'
            )
        _check_protocols(requested, 'protocols')
        object.__setattr__(self, 'protocols', requested)
        object.__setattr__(self, 'respond', respond)


class _RequirerCharm(ops.CharmBase):
    """The stand-in requirer charm. Not public; bound to its arguments by ``requirer()``.

    Constructs ``TracingEndpointRequirer`` with the protocols it was given, and the library
    does the publishing -- the request reaches the relation's application databag exactly as
    a real requirer's would, and only while the stand-in's unit is the leader, which is the
    only unit that can write it.
    """

    _options: typing.ClassVar[_RequirerOptions]

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        if not self._options.respond:
            # Join the relation and write nothing: no library object, no observers.
            return
        self.tracing = tracing.TracingEndpointRequirer(
            self, protocols=list(self._options.protocols)
        )


def _check_protocols(protocols: tuple[str, ...], argument: str) -> None:
    """Raise early where an argument names something that isn't a protocol of this interface."""
    known = sorted(_PORTS)
    unknown = [protocol for protocol in protocols if protocol not in _PORTS]
    if unknown:
        raise ValueError(
            f'{argument}={list(protocols)!r} names {unknown!r}, which the tracing interface '
            f'does not define. The protocols are {known!r}.'
        )
