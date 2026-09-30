# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""A minimal stand-in for OP089's ``ops.testing.Juju``, for this package's own tests. Not public.

OP093's stand-ins are meant to be deployed with ``ops.testing.Juju``, which doesn't exist in a
released ``ops`` yet. This is the smallest subset of it that exercises a stand-in end to end:
``deploy``, ``integrate``, ``config``, ``dispatch`` and ``settle``, with relation data carried
between the two sides after every dispatch. It is deliberately simple rather than faithful:

- Unit 0 of each application is the leader, and there are no peer relations.
- Only relation data crosses between applications. Secrets stay in the unit that owns them.
- Events are dispatched in first-in, first-out order.

When OP089 lands, tests switch from ``_juju.Juju`` to ``ops.testing.Juju`` and this module is
deleted. The names and signatures follow OP089 so that the switch is mostly an import change.
"""

from __future__ import annotations

import collections
import collections.abc
import contextlib
import dataclasses
import typing

import ops
import ops.testing

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

_SETTLE_LIMIT = 200
"""How many dispatches ``settle`` makes before deciding the model won't converge."""


class JujuError(RuntimeError):
    """The model can't do what was asked, or doesn't converge."""


class _CharmDataLike(typing.Protocol):
    @property
    def charm_type(self) -> type[ops.CharmBase]: ...
    @property
    def meta(self) -> Mapping[str, typing.Any]: ...
    @property
    def mocking(self) -> Callable[..., contextlib.AbstractContextManager[None]] | None: ...


@dataclasses.dataclass(frozen=True)
class _Plain:
    """A charm deployed from a class and metadata, with no mocking of its own."""

    charm_type: type[ops.CharmBase]
    meta: Mapping[str, typing.Any]
    mocking: None = None


class Unit:
    def __init__(self, app: App, unit_id: int, state: ops.testing.State):
        self._app = app
        self._id = unit_id
        self._state = state

    @property
    def app(self) -> App:
        return self._app

    @property
    def id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        return f"{self._app.name}/{self._id}"

    @property
    def state(self) -> ops.testing.State:
        return self._state

    def __repr__(self) -> str:
        return f"Unit({self.name!r})"


class App:
    def __init__(self, name: str, charm: _CharmDataLike, config: Mapping[str, typing.Any]):
        self._name = name
        self._charm = charm
        self._config = dict(config)
        self._units: list[Unit] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def charm(self) -> _CharmDataLike:
        return self._charm

    @property
    def config(self) -> Mapping[str, typing.Any]:
        return self._config

    @property
    def units(self) -> list[Unit]:
        return self._units

    @property
    def leader(self) -> Unit:
        return self._units[0]

    def __repr__(self) -> str:
        return f"App({self._name!r})"


@dataclasses.dataclass(frozen=True)
class _Relation:
    id: int
    interface: str
    app1: App
    endpoint1: str
    app2: App
    endpoint2: str

    def other(self, app: App) -> tuple[App, str]:
        return (self.app2, self.endpoint2) if app is self.app1 else (self.app1, self.endpoint1)

    def endpoint_of(self, app: App) -> str:
        return self.endpoint1 if app is self.app1 else self.endpoint2


@dataclasses.dataclass(frozen=True)
class Dispatch:
    event: str
    unit: Unit
    state: ops.testing.State


_EventFactory: typing.TypeAlias = (
    "Callable[[ops.testing.Context[typing.Any], ops.testing.State], typing.Any]"
)


class Juju:
    """The subset of OP089's ``ops.testing.Juju`` that this package's tests need."""

    def __init__(self) -> None:
        self._apps: dict[str, App] = {}
        self._relations: list[_Relation] = []
        self._queue: collections.deque[tuple[Unit, str, _EventFactory]] = collections.deque()
        self._next_relation_id = 1

    def __enter__(self) -> Juju:
        return self

    def __exit__(self, *exc: object) -> None:
        pass

    # -- operations --------------------------------------------------------------------------

    def deploy(
        self,
        charm: _CharmDataLike | type[ops.CharmBase],
        app: str | None = None,
        *,
        meta: Mapping[str, typing.Any] | None = None,
        num_units: int = 1,
        config: Mapping[str, typing.Any] | None = None,
    ) -> App:
        """Deploy a ``CharmData`` (or a charm class with ``meta=``). Fires no events."""
        if isinstance(charm, type):
            if meta is None:
                raise JujuError("deploying a charm class needs meta=")
            charm = _Plain(charm, meta)
        elif meta is not None:
            raise JujuError("meta= is only for deploying a charm class")
        name = app or charm.meta["name"]
        if name in self._apps:
            raise JujuError(f"an application named {name!r} is already deployed")
        application = App(name, charm, _config_defaults(charm.meta) | dict(config or {}))
        self._apps[name] = application
        for unit_id in range(num_units):
            state = ops.testing.State(
                leader=unit_id == 0, planned_units=num_units, config=application.config
            )
            application.units.append(Unit(application, unit_id, state))
        return application

    def integrate(self, app1: App | tuple[App, str], app2: App | tuple[App, str]) -> None:
        """Relate two applications, and enqueue the events ``juju integrate`` fires."""
        (a1, e1), (a2, e2) = self._resolve(app1, app2)
        interface = _endpoints(a1.charm.meta)[e1]
        relation = _Relation(self._next_relation_id, interface, a1, e1, a2, e2)
        self._next_relation_id += 1
        self._relations.append(relation)
        for app in (a1, a2):
            endpoint = relation.endpoint_of(app)
            other, _ = relation.other(app)
            for unit in app.units:
                rel = ops.testing.Relation(
                    endpoint,
                    interface=interface,
                    id=relation.id,
                    remote_app_name=other.name,
                    remote_units_data={u.id: {} for u in other.units},
                )
                unit._state = dataclasses.replace(
                    unit.state, relations={*unit.state.relations, rel}
                )
        for app in (a1, a2):
            other, _ = relation.other(app)
            for unit in app.units:
                self._enqueue(unit, "relation-created", _relation_event("created", relation.id))
                for remote in other.units:
                    self._enqueue(
                        unit, "relation-joined", _relation_event("joined", relation.id, remote.id)
                    )
                    self._enqueue(
                        unit,
                        "relation-changed",
                        _relation_event("changed", relation.id, remote.id),
                    )

    def config(self, app: App, values: Mapping[str, typing.Any]) -> None:
        """Change an application's config, and enqueue ``config-changed`` on every unit."""
        app._config.update(values)
        for unit in app.units:
            unit._state = dataclasses.replace(unit.state, config=dict(app.config))
            self._enqueue(unit, "config-changed", lambda ctx, _: ctx.on.config_changed())

    def dispatch(self, unit: Unit, event: str) -> Dispatch:
        """Run one event that arrives from outside the model -- ``update-status`` or an action.

        ``event`` is ``"update-status"`` or ``"action:<name>"``. Relation writes it makes
        propagate as for any other dispatch. Nothing is settled.
        """
        if event == "update-status":
            factory: _EventFactory = lambda ctx, _: ctx.on.update_status()  # noqa: E731
        elif event.startswith("action:"):
            name = event.removeprefix("action:")
            factory = lambda ctx, _: ctx.on.action(name)  # noqa: E731
        else:
            raise JujuError(f"dispatch() only takes update-status or an action, not {event!r}")
        return self._run(unit, event, factory)

    def settle(self) -> list[Dispatch]:
        """Drain the queue, carrying relation data between the two sides after each dispatch."""
        trace: list[Dispatch] = []
        while self._queue:
            if len(trace) >= _SETTLE_LIMIT:
                tail = ", ".join(f"{d.event}@{d.unit.name}" for d in trace[-10:])
                raise JujuError(f"the model didn't settle in {_SETTLE_LIMIT} dispatches: {tail}")
            unit, name, factory = self._queue.popleft()
            trace.append(self._run(unit, name, factory))
        return trace

    # -- internals ---------------------------------------------------------------------------

    def _enqueue(self, unit: Unit, name: str, factory: _EventFactory) -> None:
        self._queue.append((unit, name, factory))

    def _run(self, unit: Unit, name: str, factory: _EventFactory) -> Dispatch:
        charm = unit.app.charm
        ctx = ops.testing.Context(
            charm.charm_type,
            meta=_thaw(_without(charm.meta, "config", "actions")),
            config=_thaw(_as_config_meta(charm.meta)),
            actions=_thaw(charm.meta.get("actions")),
            app_name=unit.app.name,
            unit_id=unit.id,
        )
        before = unit.state
        mocking = charm.mocking() if charm.mocking is not None else contextlib.nullcontext()
        with mocking:
            after = ctx.run(factory(ctx, before), before)
        unit._state = after
        self._propagate(unit, before, after)
        return Dispatch(name, unit, after)

    def _propagate(self, unit: Unit, before: ops.testing.State, after: ops.testing.State) -> None:
        """Copy the unit's relation writes to the other side, and enqueue relation-changed."""
        for relation in self._relations:
            if unit.app not in (relation.app1, relation.app2):
                continue
            old = _find(before, relation.id)
            new = _find(after, relation.id)
            if new is None:
                continue
            app_changed = old is None or dict(old.local_app_data) != dict(new.local_app_data)
            unit_changed = old is None or dict(old.local_unit_data) != dict(new.local_unit_data)
            if not (app_changed or unit_changed):
                continue
            other, _ = relation.other(unit.app)
            for remote in other.units:
                rel = _find(remote.state, relation.id)
                assert rel is not None
                units_data = dict(rel.remote_units_data)
                units_data[unit.id] = dict(new.local_unit_data)
                replaced = dataclasses.replace(
                    rel,
                    remote_app_data=dict(new.local_app_data)
                    if unit.state.leader
                    else rel.remote_app_data,
                    remote_units_data=units_data,
                )
                remote._state = dataclasses.replace(
                    remote.state, relations={*(remote.state.relations - {rel}), replaced}
                )
                self._enqueue(
                    remote, "relation-changed", _relation_event("changed", relation.id, unit.id)
                )

    def _resolve(
        self, app1: App | tuple[App, str], app2: App | tuple[App, str]
    ) -> tuple[tuple[App, str], tuple[App, str]]:
        a1, e1 = app1 if isinstance(app1, tuple) else (app1, None)
        a2, e2 = app2 if isinstance(app2, tuple) else (app2, None)
        ends1 = _endpoints(a1.charm.meta)
        ends2 = _endpoints(a2.charm.meta)
        pairs = [
            (x, y)
            for x, ix in ends1.items()
            for y, iy in ends2.items()
            if ix == iy
            and (e1 is None or x == e1)
            and (e2 is None or y == e2)
            and _roles_match(a1.charm.meta, x, a2.charm.meta, y)
        ]
        if len(pairs) != 1:
            raise JujuError(f"can't resolve one pair of endpoints between {a1} and {a2}: {pairs}")
        ((x, y),) = pairs
        return (a1, x), (a2, y)


# -- helpers ---------------------------------------------------------------------------------


def _relation_event(kind: str, relation_id: int, remote_unit: int | None = None) -> _EventFactory:
    def factory(ctx: ops.testing.Context[typing.Any], state: ops.testing.State) -> typing.Any:
        relation = state.get_relation(relation_id)
        if kind == "created":
            return ctx.on.relation_created(relation)
        if kind == "joined":
            return ctx.on.relation_joined(relation, remote_unit=remote_unit)
        return ctx.on.relation_changed(relation, remote_unit=remote_unit)

    return factory


def relations(state: ops.testing.State, endpoint: str) -> list[ops.testing.Relation]:
    """The state's relations on ``endpoint``, typed as the non-peer relations they are.

    ``State.get_relations`` returns ``RelationBase``, which has no remote databags.
    """
    found = state.get_relations(endpoint)
    assert all(isinstance(r, ops.testing.Relation) for r in found)
    return typing.cast("list[ops.testing.Relation]", list(found))


def _find(state: ops.testing.State, relation_id: int) -> ops.testing.Relation | None:
    for relation in state.relations:
        if relation.id == relation_id and isinstance(relation, ops.testing.Relation):
            return relation
    return None


def _endpoints(meta: Mapping[str, typing.Any]) -> dict[str, str]:
    return {
        name: spec["interface"]
        for role in ("provides", "requires")
        for name, spec in meta.get(role, {}).items()
    }


def _roles_match(
    meta1: Mapping[str, typing.Any], e1: str, meta2: Mapping[str, typing.Any], e2: str
) -> bool:
    role1 = "provides" if e1 in meta1.get("provides", {}) else "requires"
    role2 = "provides" if e2 in meta2.get("provides", {}) else "requires"
    return role1 != role2


def _thaw(value: typing.Any) -> typing.Any:
    """Undo ``CharmData``'s freezing: ``ops.testing.Context`` deep-copies with pickle."""
    if isinstance(value, collections.abc.Mapping):
        return {
            k: _thaw(v) for k, v in typing.cast("Mapping[typing.Any, typing.Any]", value).items()
        }
    if isinstance(value, (list, tuple)):
        return [_thaw(v) for v in typing.cast("list[typing.Any]", value)]
    return value


def _without(meta: Mapping[str, typing.Any], *keys: str) -> dict[str, typing.Any]:
    return {k: v for k, v in meta.items() if k not in keys}


def _as_config_meta(meta: Mapping[str, typing.Any]) -> dict[str, typing.Any] | None:
    return meta.get("config")


def _config_defaults(meta: Mapping[str, typing.Any]) -> dict[str, typing.Any]:
    config: Mapping[str, typing.Any] = meta.get("config") or {}
    options: Mapping[str, Mapping[str, typing.Any]] = config.get("options", {})
    return {name: spec["default"] for name, spec in options.items() if "default" in spec}


@contextlib.contextmanager
def juju() -> Iterator[Juju]:
    """A fresh model for one test."""
    with Juju() as model:
        yield model
