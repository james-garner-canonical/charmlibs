(how-to-provide-data-for-charm-tests)=
# How to provide relation data for charm tests

This guide describes how charm interface libraries should provide relation data for charm unit tests.
By providing test data, charm libraries prevent charms from needing to know about the underlying relation data format.
Instead, charms only need to know about the library's public API and its testing API.

As the author of an interface library, you should provide a separate testing package for your library.
The testing package exposes a pair of functions, `provider()` and `requirer()`, each returning a `CharmData` that describes a *stand-in charm* for the other end of the relation — a small, real charm that answers the charm under test using your library's own implementation of the opposite side.
The stand-in is deployed alongside the charm under test with `ops.testing.Juju`, and the package also exposes a `mocked()` context manager that mocks out your library's internals for the duration of a test.

`just init --interface` scaffolds all of this for you: the package, its metadata, the two functions with their stand-in charm classes sketched and the rules below spelled out in FIXMEs, the `mocked` context manager, and a test suite covering the parts of the contract that don't depend on your interface.
Most of the work described below is implementing the stand-in charms themselves, and the tests that go with them.

Read more: {ref}`how-to-use-a-testing-package`, for using a testing package rather than writing one.

## Create a separate testing package

Your library's testing package should be distributed separately from runtime library code.
The package should be defined in a `testing` subdirectory, like this:

```
interfaces/<name>/
├── src/charmlibs/interfaces/<name>/
│   └── __init__.py
├── pyproject.toml
└── testing/
    ├── src/charmlibs/interfaces/<name>_testing/
    │   └── __init__.py
    └── pyproject.toml
```

Use these naming conventions:

- Distribution package: `charmlibs-interfaces-<hyphenated-interface-name>-testing`
- Import package: `charmlibs.interfaces.<underscored_interface_name>_testing`

## Expose a testing extra and link the package versions

Keep the library and testing package versions identical.
Releasing either one always implies releasing the other.
Also, the library and its testing package should depend on exact versions of each other.

Assuming an interface library is currently on version 1.2.3, the dependencies in the library's `pyproject.toml` file should look like this:

```toml
[project.optional-dependencies]
testing = ["charmlibs-interfaces-<name>-testing==1.2.3"]

[tool.uv.sources]
charmlibs-interfaces-my-interface-testing = { path = "testing", editable = true }

[dependency-groups]
unit = [
    # If the library's unit tests use the testing package:
    "charmlibs-interfaces-<name>[testing]",
]
```

The dependencies in `testing/pyproject.toml` file should then look like this:

```toml
[project]
dependencies = [
    "charmlibs-interfaces-<name>==1.2.3",
]

[tool.uv.sources]
charmlibs-interfaces-my-interface = { path = "..", editable = true }
```

## Implement the required testing API

Your testing package must export two functions and one context manager:

```py
def provider(*, ...) -> CharmData[ops.CharmBase]: ...
def requirer(*, ...) -> CharmData[ops.CharmBase]: ...
def mocked() -> contextlib.AbstractContextManager[None]: ...
```

`provider()` returns a stand-in that plays the *provider* role of your interface, so the charm under test is the **requirer**, and likewise `requirer()` stands in for a requirer charm and is used to test a **provider**.
If your interface has only one role worth standing in for, define only that function.

`CharmData` is the container OP089 defines in `ops.testing`: the stand-in's charm class, its `charmcraft.yaml`-shaped metadata (including any config options and actions), and the mocking scope to open around each of the stand-in's dispatches.
`ops.testing.CharmData` doesn't exist in a released `ops` yet, so each package currently defines a private placeholder of the same shape and re-exports it; when OP089 lands, the placeholder becomes an alias.

Read more: {ref}`how-to-use-a-testing-package`, which documents these functions from the charm author's side and is worth reading before implementing them.

### Name the functions for the role the *stand-in* plays

`provider()` stands in for a provider charm, so the charm under test is the **requirer**, and likewise `requirer()` stands in for a requirer charm and is used to test a **provider**.

```{important}
This is the opposite of the older `relation_for_<role>` functions that this API replaces, where the role named was the role of the *caller*.
A test that asked the old API for a provider's relation wants `requirer()`, and vice versa.
This is the single most likely thing to go wrong when migrating an existing testing package, and it goes wrong quietly, because both roles exist and both produce a deployable charm.
```

### Take only optional, keyword-only arguments

Both functions must be callable with no arguments.
Every argument must be optional and keyword-only, and each must default to the happy-path behaviour of a well-behaved application on the other end of the relation.
A test that wants an ordinary, valid relation should not have to say so.

Add whatever arguments your interface needs to let a test ask the stand-in for something other than the happy path — a refusal, a partial answer, an old wire-format version.
Invalid arguments, and invalid combinations, must raise `ValueError` when the function is called, not when the stand-in is deployed or dispatched.
Callers are not expected to catch these, so precise subtypes aren't necessary — they always indicate an error in the calling test code, and the value is in the message.

Every stand-in should accept `respond: bool = True`: `respond=False` joins the relation and writes nothing, so a test can assert on how the charm behaves while it waits.
The template scaffolds this.

Neither function takes an endpoint name or an application name.
The application name is given to `Juju.deploy(app=...)`, defaulting to the stand-in's `meta["name"]`, and the endpoints to connect are resolved by `Juju.integrate`.

### Return an immutable, reusable `CharmData`

The result must be immutable, and a single result may be deployed any number of times, in any number of tests, including concurrently in several models.
Deploying the same result twice, or the results of two calls with equal arguments, must behave identically — so consume any iterable arguments into tuples at call time, since a generator would be exhausted by the first deployment.

The returned `CharmData` has:

- **`charm_type`**: the stand-in charm class, bound to the validated arguments. The framework constructs the charm itself, as `charm_type(framework)`, so bind the arguments through the class — the recommended way is a subclass created per call, carrying the options as a class attribute:

  ```py
  def provider(*, respond: bool = True) -> CharmData[ops.CharmBase]:
      options = _ProviderOptions(respond=respond)
      charm_type = type("_ProviderCharm", (_ProviderCharm,), {"_options": options})
      return CharmData(charm_type, meta=_PROVIDER_META, mocking=mocked)
  ```

  Stand-ins run in the test process, so the arguments may be any Python object, including callables.
- **`meta`**: `charmcraft.yaml`-shaped metadata declaring exactly one non-peer endpoint, for your interface, so that `Juju.integrate` can always resolve the stand-in's side unambiguously. Name the endpoint `<interface>-provider` or `<interface>-requirer`-style where the interface has no conventional name, and document the name. `meta["name"]` should identify the library and role, such as `tls-certificates-provider`. `meta` may also declare `config` options and `actions` where they fit your library's behaviour — a stand-in that declares an action must implement it.
- **`mocking`**: your package's own `mocked`, so that `Juju` applies your library's mocking to the stand-in's dispatches.

Keep the stand-in charm classes private, and annotate the functions as returning `CharmData[ops.CharmBase]`.
Nothing a test does with a stand-in needs the concrete class, and a private class can be restructured freely.

### Write the stand-in charm

The stand-in is a real charm, and most of what there is to say about writing it is the ordinary discipline of a well-behaved charm, applied to a fixed purpose.
The rules:

- **Use the library's public API for the other role** — `TLSCertificatesProvidesV4` for the `tls-certificates` provider stand-in, for example — to read what the charm under test published and to write the answer, rather than touching the wire format. This is what keeps the stand-in's answer in agreement with the charm's question, and it makes the testing package immune to wire-format changes the library handles. Where the library has no public API for some part of the other side, the internals are allowed: the testing package is versioned in lockstep with the library and pins it exactly, so they can't drift. Say why in a comment where you do this.
- **Derive the response from what the charm under test actually published**, never from a canned value supplied by your package or by the test author. A stand-in that ignores the charm's relation data and writes fixed values reintroduces exactly the silent mismatches the package exists to prevent: relation data the charm's own library will delete and rewrite on its next reconcile, or that the charm will accept as an answer to a question it never asked. A stand-in that gets its requests from the library's API — `get_outstanding_certificate_requests()`, say — meets this by construction. Where the stand-in writes first on your interface, there is nothing to derive from, and its data comes from its arguments as ordinary fixture configuration.
- **Reconcile, don't append.** On every event the stand-in observes, it recomputes its side of the relation from the current relation data: it adds what the charm's published data now warrants, retains what is still warranted, and **removes what is no longer warranted** — an answer to a request the charm has since withdrawn, which is what the real remote charm's library does. The postcondition is "the stand-in's data is correct for this relation data", not "an answer has been appended". This is what lets `Juju.settle()` converge, and it means later turns of the conversation need nothing from your package. Mostly it's the library's job, and a library whose other side already reconciles gives it to the stand-in for free; where the stand-in adds writes of its own, they must be idempotent.
- **Never raise because of an absence of data.** Where the charm has published nothing to answer, or where the stand-in never writes on this interface at all, write nothing. A test that deploys a stand-in incidentally, while being about something else, must not be obstructed, and a charm that legitimately requests nothing still produces a model worth asserting on. Distinguish this from something the interface **cannot express** — a capability the library does not have — which must raise `ValueError` from `provider()` or `requirer()` at call time.
- **Only the leader writes application data**; each unit writes its own unit databag, where the interface uses one. The stand-in must behave correctly with any number of units.
- **Answer each relation independently**, where the stand-in is integrated with several applications at once. Where your library itself aggregates across relations — as `tracing`'s provider does, answering every relation with the union of what was requested — reproduce that, and document it.
- **Keep no state outside the model.** Charm instances are constructed afresh for each dispatch, and a `CharmData` may be deployed many times, so nothing may be written to the charm class, the options it is bound to, or module globals. Relation data, secrets, and `ops.StoredState` are the places Juju keeps state, and they are enough.
- **Every behaviour must converge under `settle()`.** A behaviour that would make the charm under test re-request forever is a bug in the stand-in, reported as a failure to settle rather than a failure of the charm. Where a behaviour changes what the charm asks for, apply it once rather than always, and record that you have in `ops.StoredState`, keyed on what is stable across the re-requests. For example, `tls-certificates`' `Outcome.renewing()` issues a certificate already due for renewal, and the requirer library responds by re-requesting — so the stand-in applies it only to the first certificate it issues for each set of request attributes, and answers the re-request normally. Document where your behaviours apply once.

### Define `mocked`, even if it does nothing

`mocked()` mocks out your library's own internals for the duration of a test.
Some libraries need this — anything that manages Kubernetes resources outside the Juju model, for instance — and some have nothing to mock.

The requirements are the same either way:

- It must be callable with no arguments. Optional keyword-only arguments are allowed; required ones are not.
- Only your own library's internals may be mocked. Nothing defined outside the library, so that charm code which doesn't pass through your library has no side effects.
- It must be [reentrant](https://docs.python.org/3/library/contextlib.html#reentrant-context-managers), so that a fixture and the test that uses it may each open a scope, and so that several libraries' scopes nest in any order.
- **Every** library must define it, including one that currently mocks nothing, in which case it is a no-op. A library that didn't define it would break every test written against it on the day it started mocking something; defining it from the start makes introducing mocking a non-breaking change.

`Juju` opens the scope around every dispatch it makes — it is the stand-in's `CharmData.mocking`, and one of the default mocks for the charm under test — and a test opens it itself when it runs the charm with `ops.testing.Context` directly.
So the testing package does not check that a scope is open: a test that forgets gets the library's real behaviour, which is slower or has side effects, but is not wrong.

Mocking can change what a charm's unit tests see, so let your library's version reflect that: substantial changes to mocking warrant a minor version bump rather than a patch bump, and truly breaking changes to testing should be avoided within a major version of the library.

The purpose of mocking is to remove side effects and costs that make a test impossible or intolerably slow.
Reproducible databag contents are welcome if they follow, but are not the goal, and `mocked` is not required to make time-dependent content — a certificate's validity period, say — reproducible.

### Write the conformance tests

Two properties of the contract can't be checked by reading a signature, and the design depends on both, so each testing package must test them:

1. **The response is derived, not canned.** Deploy two charms that ask for **different** things, integrate both with one stand-in, and assert that the stand-in's data differs accordingly — not merely that it is non-empty. For a role where the stand-in writes first there is nothing to derive, and this test does not apply.
2. **The stand-in reconciles.** After the charm under test changes what it asks for and the model settles, the stand-in's answer to the old request is gone.

`just init --interface` scaffolds both as skipped placeholders with instructions, in `testing/tests/unit/test_testing.py`.
Worked examples are `test_provider_derives_its_answer_from_what_the_charm_published` and `test_provider_reconciles_when_the_charm_changes_what_it_asks_for` in `interfaces/tls-certificates/testing/tests/unit/test_testing.py`.

These tests double as the package's examples.

### Worked examples

Three testing packages in the monorepo implement this design, and are worth reading whole:

- `interfaces/tls-certificates/testing/` — a request-response interface. The provider stand-in derives its answers from the charm's published requests, applies one-shot behaviours through `ops.StoredState`, and goes through the library's internals for the one write the public API can't express. The requirer stand-in constructs the library's requirer object with its arguments and lets the library do the publishing.
- `interfaces/tracing/testing/` — a provider stand-in that reproduces its library's aggregation across relations rather than answering each independently.
- `interfaces/certificate_transfer/testing/` — a one-way interface, where what is derived is not the answer but the wire-format version it's written in, and where reconciling means removing as well as adding.

## Test the testing package

The testing package should have its own test suites like any other package.
It should only have unit tests, since the package itself only targets use in unit tests.

`just init --interface` scaffolds tests covering the parts of the contract that don't depend on your interface: that both functions are callable with no arguments and take only keyword-only arguments, that the result is an immutable `CharmData` with exactly one endpoint and the package's own `mocked`, that invalid arguments raise `ValueError` at call time, and that `respond=False` writes nothing.
It also scaffolds skipped placeholders for the tests only you can write — the conformance tests above, and tests of what your stand-in writes.

Until OP089's `ops.testing.Juju` is released, the scaffolded suite drives the stand-ins with a minimal private harness of the same shape, in `testing/tests/unit/_juju.py`.
When `Juju` lands, the tests switch to it and the harness is deleted.

In the `charmlibs` monorepo, the testing package's tests are run automatically in CI whenever the interface package or its testing package are changed.
You can run the tests locally like this:

```
just unit interfaces/<interface name>/testing
```

## Example usage in charm tests

Charms should specify the version of the library that they need in their dependencies.
In their testing dependencies, they should require the library's `testing` extra, but not specify any version constraints.

A charm author deploys the stand-in for the role opposite their charm's, integrates it, and lets the model settle:

```python
from charmlibs.interfaces import my_interface_testing


def test_the_happy_path(juju: testing.Juju):
    # The charm under test is the requirer, so the stand-in is the provider.
    app = juju.deploy(MyCharm)
    remote = juju.deploy(my_interface_testing.provider())
    juju.integrate((app, "my-endpoint"), remote)
    juju.settle()
    assert app.leader.state.unit_status == testing.ActiveStatus()
```

Later turns of the conversation are more operations on the model and another `settle()`:

```python
def test_a_later_turn(juju: testing.Juju):
    app = juju.deploy(MyCharm)
    remote = juju.deploy(my_interface_testing.provider())
    juju.integrate((app, "my-endpoint"), remote)
    juju.settle()
    juju.config(app, {"some-option": "new-value"})  # the charm asks for something else
    juju.settle()  # the stand-in drops the stale answer and answers the new request
    assert app.leader.state.unit_status == testing.ActiveStatus()
```

```{tip}
Charms should always depend on `charmlibs-interfaces-<name>[testing]`, not directly on `charmlibs-interfaces-<name>-testing`.
This ensures that the testing package version always matches the library itself.
```

Read more: {ref}`how-to-use-a-testing-package`, which is the charm author's side of everything above.
