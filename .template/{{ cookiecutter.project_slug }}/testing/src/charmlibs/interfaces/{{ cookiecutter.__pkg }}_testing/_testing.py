# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The stand-in charms: :func:`provider` and :func:`requirer`."""

from __future__ import annotations

import dataclasses
import typing

import ops

# from charmlibs.interfaces import {{ cookiecutter.__pkg }}
from ._charm_data import CharmData
from ._mocking import mocked

if typing.TYPE_CHECKING:
    from collections.abc import Mapping

_PROVIDER_META: Mapping[str, typing.Any] = {
    'name': '{{ cookiecutter.project_slug }}-provider',
    'provides': {'endpoint': {'interface': '{{ cookiecutter.project_slug }}'}},
}
"""The stand-in provider's metadata. One endpoint, so ``Juju.integrate`` resolves it."""

_REQUIRER_META: Mapping[str, typing.Any] = {
    'name': '{{ cookiecutter.project_slug }}-requirer',
    'requires': {'endpoint': {'interface': '{{ cookiecutter.project_slug }}'}},
}
"""The stand-in requirer's metadata. One endpoint, so ``Juju.integrate`` resolves it."""


def provider(*, respond: bool = True) -> CharmData[ops.CharmBase]:
    """Return a stand-in ``{{ cookiecutter.project_slug }}`` provider, for testing a **requirer** charm.

    Deploy it with ``ops.testing.Juju`` and integrate it with the charm under test::

        juju = ops.testing.Juju()
        app = juju.deploy(MyCharm)
        remote = juju.deploy({{ cookiecutter.__pkg }}_testing.provider())
        juju.integrate((app, 'endpoint'), remote)
        juju.settle()

    The stand-in's endpoint is named ``endpoint``; ``Juju.integrate`` resolves it
    unambiguously, since it is the stand-in's only one.

    FIXME: add optional, keyword-only arguments customising what this provider does, each
    defaulting to the happy-path behaviour of a well-behaved provider. Validate them into
    ``_ProviderOptions``, which raises ``ValueError`` at call time for anything invalid.

    Args:
        respond: Whether the stand-in answers at all. ``respond=False`` joins the
            relation and writes nothing, so a test can assert on how the charm behaves
            while it waits for an answer.

    Returns:
        A ``CharmData`` describing the stand-in charm, for ``Juju.deploy``.
    """
    options = _ProviderOptions(respond=respond)
    charm_type = type('_ProviderCharm', (_ProviderCharm,), {'_options': options})
    return CharmData(charm_type, meta=_PROVIDER_META, mocking=mocked)


def requirer(*, respond: bool = True) -> CharmData[ops.CharmBase]:
    """Return a stand-in ``{{ cookiecutter.project_slug }}`` requirer, for testing a **provider** charm.

    Deploy it with ``ops.testing.Juju`` and integrate it with the charm under test::

        juju = ops.testing.Juju()
        app = juju.deploy(MyCharm)
        remote = juju.deploy({{ cookiecutter.__pkg }}_testing.requirer())
        juju.integrate((app, 'endpoint'), remote)
        juju.settle()

    The stand-in's endpoint is named ``endpoint``; ``Juju.integrate`` resolves it
    unambiguously, since it is the stand-in's only one.

    FIXME: add optional, keyword-only arguments customising what this requirer asks for,
    each defaulting to the happy-path behaviour of a well-behaved requirer. Validate them
    into ``_RequirerOptions``, which raises ``ValueError`` at call time for anything
    invalid.

    Args:
        respond: Whether the stand-in publishes at all. ``respond=False`` joins the
            relation and writes nothing, so a test can assert on how the charm behaves
            with a silent requirer.

    Returns:
        A ``CharmData`` describing the stand-in charm, for ``Juju.deploy``.
    """
    options = _RequirerOptions(respond=respond)
    charm_type = type('_RequirerCharm', (_RequirerCharm,), {'_options': options})
    return CharmData(charm_type, meta=_REQUIRER_META, mocking=mocked)


# ---------------------------------------------------------------------- the stand-in charms


@dataclasses.dataclass(frozen=True)
class _ProviderOptions:
    """The validated arguments of one ``provider()`` call. Not public.

    FIXME: add a field per ``provider()`` argument. Validate in ``__post_init__`` and
    raise ``ValueError`` for anything invalid, so misuse fails at call time rather than
    when the stand-in is deployed. Consume any iterable arguments into tuples, so that a
    stand-in really is reusable: a generator would otherwise be consumed by the first
    deployment and empty for the second.
    """

    respond: bool


class _ProviderCharm(ops.CharmBase):
    """The stand-in provider charm. Not public; bound to its arguments by ``provider()``.

    FIXME: implement the stand-in, following OP093's rules:

    - **Use the library's public API for the other role** -- the provider side of
      ``charmlibs.interfaces.{{ cookiecutter.__pkg }}`` -- to read what the charm under
      test published and to write the answer, rather than touching the wire format. Where
      the library has no public API for some part of it, the library's internals are
      allowed: this package and the library are released in lockstep and pin each other
      exactly. Say why in a comment where you do.
    - **Derive the response from what the charm under test actually published**, never
      from a canned value. Where the provider writes first on this interface there is
      nothing to derive from, and the data comes from ``provider()``'s arguments instead.
    - **Reconcile, don't append.** On every event observed, recompute this side of the
      relation from the current relation data: add what is now warranted, keep what is
      still warranted, and remove what is no longer warranted -- an answer to a request
      the charm has since withdrawn, say. Mostly the library does this for you. The
      postcondition is "the stand-in's data is correct for this relation data", which is
      also what lets ``Juju.settle()`` converge.
    - **Never raise because of an absence of data.** Where the charm has published
      nothing to answer, write nothing.
    - **Only the leader writes application data**; each unit writes its own unit databag,
      where the interface uses one.
    - **Answer each relation independently**, where the interface's answers are per
      relation rather than per application.
    - **Keep no state outside the model.** Charm instances are constructed afresh for
      each dispatch, so nothing may be written to the charm class, the options, or module
      globals. ``ops.StoredState`` is fine.
    - **Every behaviour must converge** under ``settle()``. Where a behaviour would make
      the charm under test re-request forever, apply it once -- record that you have in
      ``ops.StoredState``, keyed on what is stable across the re-requests.
    """

    _options: typing.ClassVar[_ProviderOptions]

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        if not self._options.respond:
            # Join the relation and write nothing: no library object, no observers.
            return
        # FIXME: construct the library's provider object, and observe the events it
        # answers on -- typically the library's own request event, or relation-changed::
        #
        #     self.lib_obj = {{ cookiecutter.__pkg }}.<...>Provider(self, 'endpoint', ...)
        #     framework.observe(self.lib_obj.on.<...>, self._reconcile)
        #
        # Then reconcile: read what the charm under test published through the library,
        # and write the answer through the library. Only the leader writes application
        # data -- return early where ``not self.unit.is_leader()`` and the library would
        # raise.


@dataclasses.dataclass(frozen=True)
class _RequirerOptions:
    """The validated arguments of one ``requirer()`` call. Not public.

    FIXME: as for ``_ProviderOptions``.
    """

    respond: bool


class _RequirerCharm(ops.CharmBase):
    """The stand-in requirer charm. Not public; bound to its arguments by ``requirer()``.

    FIXME: implement the stand-in, following the same rules as ``_ProviderCharm``. Where
    the requirer writes first on this interface -- the usual case for a request-response
    interface -- there is nothing to derive from the charm under test, and the request is
    supplied by ``requirer()``'s arguments as ordinary fixture configuration.
    """

    _options: typing.ClassVar[_RequirerOptions]

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        if not self._options.respond:
            # Join the relation and write nothing: no library object, no observers.
            return
        # FIXME: construct the library's requirer object with what ``requirer()`` was
        # given, and let the library do the publishing::
        #
        #     self.lib_obj = {{ cookiecutter.__pkg }}.<...>Requirer(self, 'endpoint', ...)
