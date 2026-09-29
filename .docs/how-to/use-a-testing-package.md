---
myst:
  html_meta:
    description: Use an interface library's testing package to write state-transition tests for your charm, without knowing the relation's wire format.
---

(how-to-use-a-testing-package)=
# How to use a testing package in state-transition tests
% Based on: OP093 - Charm library testing API

Every `charmlibs.interfaces` library ships a companion *testing package*, which stands in for the application on the other end of the relation while you test your charm. Using it means your charm's tests never touch the relation's wire format: they deploy a stand-in charm, integrate it with yours, let the model settle, and assert on what your charm did.

This guide covers what is true of every testing package. For the arguments a particular library accepts — what its stand-in can be asked to do — see that library's own how-to guide and reference docs.

```{note}
The API shown here is the one proposed by OP089 — *Multiple-charm state transition tests* — whose `ops.testing.Juju` is not yet released. Until it ships, each testing package's own test suite drives the stand-ins with a minimal private harness of the same shape, so the packages are real and tested today; what is pending is the `ops.testing` side of the examples below. When `Juju` lands, the examples work as written.
```

Read more: {ref}`how-to-provide-data-for-charm-tests`, for writing a testing package rather than using one.

## Install the testing package

Add the library's `testing` extra to your test dependencies:

```toml
[dependency-groups]
unit = [
    "charmlibs-interfaces-<name>[testing]",
]
```

Depend on the extra rather than on `charmlibs-interfaces-<name>-testing` directly. The two distributions pin each other exactly, and going through the extra is what keeps the version of the testing package you get matched to the version of the library your charm uses.

Then import the testing package alongside the library:

```py
from charmlibs.interfaces import my_interface, my_interface_testing
```

## The stand-in charm

A testing package exposes two functions, `provider()` and `requirer()`. Each returns a `CharmData` — a charm class plus `charmcraft.yaml`-shaped metadata — describing a **stand-in charm**: a small, real charm that plays the other end of the relation, reading and writing through the library's own implementation of the opposite side.

The function is named for the role the *stand-in* plays, so the charm under test plays the opposite one: a requirer charm is tested with `provider()`, and a provider charm with `requirer()`.

Both functions are callable with no arguments. Every argument is optional and keyword-only, and defaults to the happy path — a typical, valid, well-behaved remote. One argument every stand-in shares is `respond`: `respond=False` gives you a stand-in that joins the relation but writes nothing, so you can assert on how your charm behaves while it waits for an answer.

The result is immutable, and a single result can be deployed any number of times, in any number of tests. Stand-ins run in the test process, so arguments can be any Python object — including callables, where a library offers per-request behaviour.

## Deploy and integrate the stand-in

Deploy the stand-in alongside your charm with `ops.testing.Juju`, integrate the two, and let the model settle:

```py
import pytest
from ops import testing

from charmlibs.interfaces import tls_certificates_testing

from charm import MyCharm


@pytest.fixture()
def juju():
    with testing.Juju() as juju:
        yield juju


def test_the_happy_path(juju: testing.Juju):
    app = juju.deploy(MyCharm)
    ca = juju.deploy(tls_certificates_testing.provider())
    juju.integrate((app, "certificates"), ca)
    juju.settle()
    assert app.leader.state.unit_status == testing.ActiveStatus()
```

`Juju.deploy` takes the charm class from the `CharmData` and its metadata, config and actions from its `meta`, and opens the package's `mocked()` scope around each of the stand-in's dispatches. The application name defaults to the stand-in's own; pass `app=` to choose one, which you must do when deploying the same stand-in twice. `Juju.integrate` resolves the stand-in's endpoint unambiguously, because its metadata declares exactly one; give your charm's endpoint as an `(app, endpoint)` tuple where it has more than one endpoint for the interface.

`Juju.settle()` dispatches events on both sides until nothing changes. Because the stand-in reconciles — it recomputes its side of the relation from whatever your charm has published, dropping answers to requests your charm has withdrawn — the two sides reach a fixed point, and the state you assert on is a genuinely settled one.

The stand-in's own state is available too, which makes cross-application assertions a check on two states:

```py
def test_the_provider_answered_every_unit(juju: testing.Juju):
    app = juju.deploy(MyCharm, num_units=3)
    ca = juju.deploy(tls_certificates_testing.provider())
    juju.integrate((app, "certificates"), ca)
    juju.settle()
    (relation,) = ca.leader.state.get_relations("certificates")
    assert len(json.loads(relation.local_app_data["certificates"])) == 3
```

## The positions a test can reach

Relations follow a small number of request-response patterns, and a test wants its charm in one of a few positions within the conversation. All but one are directly reachable:

| Position | How |
|---|---|
| The charm hasn't been related | Don't integrate |
| Related, and the stand-in hasn't written | `provider(respond=False)` |
| The stand-in has written, and the charm has reacted | `settle()` |
| The stand-in has written, and the charm hasn't reacted yet | Not currently reachable |

The last position — the answer on the wire, the charm not yet run for it — is where you would pin down "blocked while it waits for the certificate to be read". `settle()` always runs to convergence, so the charm's `relation-changed` fires before control returns. Reaching it needs OP089 to let `settle()` stop at a chosen dispatch; until then, assert on the settled state, or on the unanswered position with `respond=False`.

## Single-event tests after settling

A settled unit's `State` is the input to ordinary single-charm tests. Build an `ops.testing.Context` for your charm as usual, and run any event against `unit.state`:

```py
def test_update_status_stays_active(juju: testing.Juju):
    app = juju.deploy(MyCharm)
    juju.integrate((app, "certificates"), juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    ctx = testing.Context(MyCharm)
    with tls_certificates_testing.mocked():
        state_out = ctx.run(ctx.on.update_status(), app.leader.state)
    assert state_out.unit_status == testing.ActiveStatus()
```

Open the library's `mocked()` scope yourself here: nothing `Juju` applies reaches a `Context.run` you make yourself. This is also how to test behaviour that needs the charm patched — a workload version, a clock — where the patch must be in place for the run.

## Later turns of the conversation

A later turn — after a config change, a key rotation, or anything else that makes your charm publish again — is more operations on the model and another `settle()`:

```py
def test_certificate_renewal(juju: testing.Juju):
    app = juju.deploy(MyCharm)
    ca = juju.deploy(tls_certificates_testing.provider())
    juju.integrate((app, "certificates"), ca)
    juju.settle()
    # The charm rotates its key and withdraws its old certificate signing request.
    juju.config(app, {"key-size": 4096})
    # The stand-in drops the answer to the withdrawn request and answers the new one.
    juju.settle()
    assert app.leader.state.unit_status == testing.ActiveStatus()
```

The change that drives the turn must happen *in the model* — a config change, an action on your charm — so that the stand-in sees its effects. A change made in a single-charm `Context.run` never reaches the stand-in.

## Changing the stand-in's behaviour partway through

A stand-in is deployed once per test, with fixed arguments. Where a test needs its behaviour to change partway through, there are three routes, in order of preference:

- **`Juju.config`**, where the stand-in declares a config option for the behaviour: for a stand-in with an `outcome` option, `juju.config(ca, {"outcome": "denied"})`, then `settle()`. None of the current testing packages declare config options yet.
- **An action** on the stand-in, where the behaviour is a verb with no config shape, such as revoking everything it has issued. This needs OP089 to run actions on a deployed application.
- **Replacing the application**: remove the relation, deploy a stand-in built with different arguments, and integrate again. This always works.

A library declares config options for whatever behaviour has a natural config shape; its own guide says which route it offers. The last route is the fallback for everything else.

## The `mocked()` scope

Every testing package exposes a `mocked()` context manager, which mocks out the library's own internals — nothing defined outside the library — for the duration of the scope. It is used in three places:

- **Around the stand-in's dispatches**, opened by `Juju`, because it is the `mocking` of the `CharmData` that `provider()` and `requirer()` return.
- **Around your charm's dispatches**, opened by `Juju`'s default mocks for each library your charm uses — or by you, where that isn't available, which is what a `mocked` fixture is for:

  ```py
  @pytest.fixture()
  def mocked():
      with tls_certificates_testing.mocked():
          yield
  ```

- **Around single-charm tests**, opened by you, when you run your charm with `ops.testing.Context` yourself.

The scope is reentrant, so a fixture and the test that uses it may each open one, and several libraries' scopes stack in any order:

```py
@pytest.fixture()
def mocked():
    with (
        tls_certificates_testing.mocked(),
        certificate_transfer_testing.mocked(),
    ):
        yield
```

There is no "must be inside the scope" rule. A test that runs the charm with `Context` and forgets to open it gets the library's real behaviour — slower, or with side effects, but not wrong. A test that needs a library mocked but has no interest in the relation can open the scope alone.

## Shared limitations

**`ops.testing.Juju` is not released yet.** The examples above are written against OP089's proposed API. Until it ships, the testing packages' own suites exercise the stand-ins through a minimal private harness of the same shape; that harness is not part of the packages' public API and isn't something to use in your own tests.

**The "answered but not seen" position is unreachable.** `settle()` runs to convergence, so you can't leave the stand-in's answer on the wire with your charm not yet run for it. See the positions table above.

**Stand-ins run in-process.** A stand-in executes in the test process, against the test's copy of the library. That is what allows callable arguments, and it means the stand-in always speaks the library version you test against — which is the version your charm uses, since the two packages pin each other.

**Some data isn't reproducible byte-for-byte.** Time-dependent content — a certificate's validity period, say — comes from the real clock, and `mocked()` is not required to fix it. Assert on what the library reports rather than on bytes, and rely on settling, not byte equality, to check that nothing was rewritten.
