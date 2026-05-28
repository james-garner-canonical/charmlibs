# Plan: Comprehensive Error-Path Test Coverage for Snap Library

> **Shell**: We are in **fish**. Do not use bash-only syntax. In particular:
> - `for` loops use `end` not `done`: `for f in *.json; echo $f; end`
> - Do NOT run terminal commands to read capture JSON — use `read_file` directly on `snap/.report/capture/*.json` instead (no approval required).
>
> **Output capture**: **Always** run commands via `.scripts/output-wrapper.sh`. This writes stdout+stderr to `.out`. Read `.out` afterwards to check results — it is plain text and `grep` / `tail` / `cat` work normally on it.
>
> **Just commands**: Always use `just` commands when one exists (e.g. `just lint snap`, `just unit snap`, `just format snap`). Do not call `uv`, `pytest`, `ruff`, etc. directly.
>
> **`-k` quoting**: To pass a multi-token `-k` expression (with `or`/`and`) through `just`, wrap it in single-then-double quotes: `-k '"TestFoo or TestBar"'`. Fish passes the double-quoted string literally to just; just strips the outer double quotes; pytest receives the full expression. Example: `-k '"TestInstallAdditionalErrors or TestRefreshAdditionalErrors"'`. Single-token patterns need no extra quoting: `-k _capture`.

## Goal

Ensure every public function in the snap library has tests covering all realistic failure conditions. For each endpoint module, discover what errors the real snapd API returns, then add both functional and unit tests with precise error type assertions.

## Checklist

Work through the next module in the list. Your task is done when you finish this module, and you'll report completion to the user after finishing that module.

- [x] `_snapd_snaps` — snap lifecycle (info, install, remove, refresh, hold, unhold)
- [x] `_snapd_conf` — snap configuration (get, set, unset)
- [x] `_snapd_apps` — snap services (start, stop, restart)
- [x] `_snapd_interfaces` — snap interfaces (connect, disconnect)
- [x] `_snapd_aliases` — snap aliases (alias, unalias)
- [ ] `_snapd_logs` — snap logs (logs)
- [ ] `_functions` — high-level helpers (ensure, ensure_revision)
- [ ] `_client` — connection errors, timeouts, async change failures (unit tests only)

## Missing Error Scenarios Per Module

### `_snapd_snaps` (snap/src/charmlibs/snap/_snapd_snaps.py)

Tests: `snap/tests/functional/test_snapd_snaps.py`, `snap/tests/unit/test_snapd_snaps.py`

| Function | Scenario | Priority | Notes |
|----------|----------|----------|-------|
| `install` | Snap name doesn't exist in store | Done | `SnapNotFoundError`, kind `snap-not-found` |
| `install` | Invalid channel format (e.g. `"garbage"`) | Done | `SnapAPIError`, kind `snap-channel-not-available` (no specific subclass) |
| `install` | Revision not available | Done | `SnapRevisionNotAvailableError` |
| `install` | Classic snap without `classic=True` | Done | Already tested |
| `refresh` | Invalid channel format | Done | `SnapAPIError`, kind `snap-channel-not-available` |
| `refresh` | Revision not available for installed snap | Done | `SnapRevisionNotAvailableError` |
| `refresh` | Snap not installed (empty kind — base `SnapError`) | Done | Already tested |
| `remove` | Snap name that truly doesn't exist (vs just not installed) | Done | Same as not-installed — `SnapNotInstalledError`, returns `False` |
| `remove` | Remove with `purge=True` when not installed | Done | Same as without purge — returns `False` |
| `hold` | Hold an already-held snap | Done | Idempotent — no error |
| `_list_channels` | Snap name not in store | Done | `SnapNotFoundError`, kind `snap-not-found` |
| `install` | Strict snap with `classic=True` | Low | Probably ignored, but could error |

### `_snapd_conf` (snap/src/charmlibs/snap/_snapd_conf.py)

Tests: `snap/tests/functional/test_snapd_conf.py`, `snap/tests/unit/test_snapd_conf.py`

| Function | Scenario | Priority | Notes |
|----------|----------|----------|-------|
| `get` | Snap not installed | Done | `SnapOptionNotFoundError` (surprising but verified) |
| `set` | Snap not installed | Done | `SnapNotFoundError` |
| `unset` | Snap not installed | Done | `SnapNotFoundError` |
| `set` | Empty config dict `{}` | Done | No-op — accepted without error |
| `set` | Config with deeply nested dict | Done | Works — existing `test_set_and_get_dict` roundtrip |
| `get` | Dotted key path (e.g. `"core.https_address"`) | Done | Works — tested via `_get_one` |
| `get` | Multiple keys where some exist and some don't | Done | Raises `SnapOptionNotFoundError` for first missing key; no partial results |
| `unset` | Key that uses dotted path | Done | Works without error |

### `_snapd_apps` (snap/src/charmlibs/snap/_snapd_apps.py)

Tests: `snap/tests/functional/test_snapd_apps.py`, `snap/tests/unit/test_snapd_apps.py`

Most error paths are already well-covered. Remaining:

| Function | Scenario | Priority | Notes |
|----------|----------|----------|-------|
| `start` | Snap installed but has zero services, called with no service arg (just snap name) | Medium | Distinct from nonexistent service? `start('hello-world')` vs `start('hello-world', 'svc')` |
| `stop` | Same — snap with no services, no service arg | Medium | |
| `restart` | Same — snap with no services, no service arg | Medium | |

### `_snapd_interfaces` (snap/src/charmlibs/snap/_snapd_interfaces.py)

Tests: `snap/tests/functional/test_snapd_interfaces.py`, `snap/tests/unit/test_snapd_interfaces.py`

| Function | Scenario | Priority | Notes |
|----------|----------|----------|-------|
| `connect` | Slot snap doesn't exist | Medium | Different error from plug snap not existing? |
| `connect` | Snap installed but plug doesn't exist | Done | Already tested (`SnapError`, no kind) |
| `disconnect` | Nonexistent plug/slot on installed snap | Medium | Distinct from not-connected? |
| `disconnect` | `forget=True` on a connected interface | Medium | Verify it works |
| `disconnect` | `forget=True` on a not-connected interface | Medium | Error or no-op? |
| `connect` | Both plug and slot specified but interface types are incompatible | Low | Hard to set up; might need specific snaps |

### `_snapd_aliases` (snap/src/charmlibs/snap/_snapd_aliases.py)

Tests: `snap/tests/functional/test_snapd_aliases.py`, `snap/tests/unit/test_snapd_aliases.py`

| Function | Scenario | Priority | Notes |
|----------|----------|----------|-------|
| `alias` | Alias name that already exists (same snap+app) | Medium | Idempotent or error? |
| `alias` | Alias name that already exists (different snap) | Medium | Conflict error? |
| `alias` | Empty or invalid alias name | Low | |
| `unalias` | Alias created, snap removed, then unalias | Medium | Does the alias survive snap removal? |

### `_snapd_aliases` (completed)

- `alias()` is fully idempotent when called twice with the same snap+app+alias_name — no error, second call succeeds silently.
- Calling `alias()` with the same alias name but a different app of the **same snap** also succeeds silently — snapd reassigns the alias to the new app without error.
- Only trying to claim an alias already held by a **different snap** raises `SnapChangeError` with "already enabled for" in the message.
- Trying to claim an alias name already held by a different snap raises `SnapChangeError` with "already enabled for" in the message.
- Aliases do **not** survive snap removal. Calling `unalias()` after the snap is removed raises `SnapAPIError` with empty kind and "cannot find manual alias" in the message — identical to calling `unalias()` on a never-created alias.
- `hello-world` snap's app name is `hello-world`, not `hello` — important for test setup; the existing `test_alias_not_installed_snap_raises` works because snapd rejects with `snap-not-installed` before checking the app name.
- No new error classes needed (all new scenarios map to existing `SnapChangeError` or base `SnapAPIError`).
- No new unit tests added — `alias()` and `unalias()` have no conditional logic; existing body-construction tests are sufficient.

### `_snapd_logs` (snap/src/charmlibs/snap/_snapd_logs.py)

Tests: `snap/tests/functional/test_snapd_logs.py`, `snap/tests/unit/test_snapd_logs.py`

| Function | Scenario | Priority | Notes |
|----------|----------|----------|-------|
| `logs` | Snap not installed | Done | `SnapNotFoundError` |
| `logs` | Snap with no services | Done | `SnapAppNotFoundError` |
| `logs` | `num_lines=0` | Medium | Empty list? Error? |
| `logs` | Snap name that doesn't exist at all | Medium | Same as not installed? Different? |
| `logs` | No snap args — all system logs | Low | Might return a lot; verify it works |
| `logs` | Negative `num_lines` | Low | Snapd behaviour unknown |

### `_functions` (snap/src/charmlibs/snap/_functions.py)

Tests: `snap/tests/functional/test_functions.py`, `snap/tests/unit/test_functions.py`

Coverage is already excellent. No new error scenarios identified.

### `_client` (snap/src/charmlibs/snap/_client.py)

Tests: unit tests only — `snap/tests/unit/test_client.py` (new file)

All modules call through `_client.get/post/put` → `_request` → `_request_raw`. Connection and timeout errors propagate identically regardless of which module initiates the call, so they only need to be tested once at the `_client` level.

**`_request_raw` error paths (lines 159–175):**

| Scenario | Error raised | Kind | Notes |
|----------|-------------|------|-------|
| Snapd socket not found (`FileNotFoundError`) | `SnapConnectionError` | `charmlibs-snap-socket-not-found` | e.g. snapd not installed, or non-root without socket access |
| Other `URLError` (connection refused, permission denied) | `SnapConnectionError` | `charmlibs-snap-connection-error` | |
| Request times out (`TimeoutError`) | `SnapTimeoutError` | `charmlibs-snap-request-timeout` | After `_REQUEST_TIMEOUT` (30s) |

**`_wait_for_change` error paths (lines 183–226) — affects all async (POST) operations:**

| Scenario | Error raised | Kind | Notes |
|----------|-------------|------|-------|
| Change poll exceeds deadline | `SnapTimeoutError` | `charmlibs-snap-change-timeout` | After `_CHANGE_TIMEOUT` (600s) |
| Change enters `Error` state | `SnapChangeError` | `charmlibs-snap-change-error` | e.g. snap download fails, hook errors |
| Unexpected change status | `SnapChangeError` | `charmlibs-snap-change-unknown` | Defensive; shouldn't happen in practice |

**`_request` response parsing error paths:**

| Scenario | Error raised | Kind | Notes |
|----------|-------------|------|-------|
| Invalid JSON in response body | `SnapBadResponseError` | `charmlibs-snap` | |
| Response is not a dict | `SnapBadResponseError` | `charmlibs-snap` | |
| Missing `type` or `result` key | `SnapBadResponseError` | `charmlibs-snap` | |

**Modules with async operations** (affected by `_wait_for_change` errors): `_snapd_snaps` (install, remove, refresh, hold, unhold), `_snapd_conf` (set, unset), `_snapd_apps` (start, stop, restart), `_snapd_interfaces` (connect, disconnect), `_snapd_aliases` (alias, unalias). These all POST and get back `type: async`, so a `SnapChangeError` or `SnapTimeoutError` from `_wait_for_change` can bubble up from any of them. Testing at `_client` level is sufficient — no need to repeat per module.

---

## Working Strategy

Every agent executing a step in this plan MUST follow this exact workflow. Do not invent your own approach.

### Prerequisites

Read `snap/AGENTS.md` — it contains the exact commands for lint, unit, and functional tests, plus how to query the snapd API directly. **All commands in snap/AGENTS.md already use `.scripts/output-wrapper.sh`** — follow them as-is.

Before making changes, run the checks to confirm a clean baseline. If there are preexisting failures, stop and report them:

```bash
just format snap
.scripts/output-wrapper.sh just lint snap
# read .out
.scripts/output-wrapper.sh just unit snap
# read .out
multipass exec --working-directory '/home/ubuntu/charmlibs' snap-sandbox -- \
  .scripts/output-wrapper.sh sudo env UV_PROJECT_ENVIRONMENT=/tmp/sudo-snap-venv just functional snap
# read .out
```

**When running functional tests via `run_in_terminal`:** use `mode=sync` with `timeout=360000` (6 minutes). This avoids polling — the result is returned directly once the suite finishes. If the timeout is hit, it falls back to returning a terminal ID (same as async), so you can still poll with `get_terminal_output` as a fallback.

### Step 1: Identify gaps

Read the source module and its existing functional + unit test files. List every function and identify which error scenarios are NOT yet tested. Refer to the table above but also think about what else could go wrong — the tables are a starting point, not exhaustive.

### Step 2: Write exploratory capture tests

Write capture tests **directly in the existing functional test file** for the module (e.g. `snap/tests/functional/test_snapd_snaps.py`). Do NOT create a separate file. Add them at the very end of the file, in a clearly marked section:

```python
# ---------------------------------------------------------------------------
# EXPLORATORY: capture error responses (to be replaced with assertions)
# ---------------------------------------------------------------------------

_CAPTURE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / '.report' / 'capture'


def _exc_dict(exc: Exception) -> dict:
    return {
        'exception_class': type(exc).__name__,
        'kind': getattr(exc, 'kind', None),
        'message': getattr(exc, 'message', str(exc)),
        'value': str(getattr(exc, 'value', None)),
        'status_code': getattr(exc, '_status_code', None),
        'status': getattr(exc, '_status', None),
    }


def _run_and_capture(name: str, monkeypatch, call):
    """Call *call*, capture the raw API error response and/or the exception."""
    from charmlibs.snap import _client

    _CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

    raw: dict = {}
    orig_make_error = _client._make_error

    def patched_make_error(response):
        raw.update(response)
        return orig_make_error(response)

    monkeypatch.setattr(_client, '_make_error', patched_make_error)

    exc: Exception | None = None
    try:
        call()
    except Exception as e:
        exc = e

    data: dict = {}
    if raw:
        data['raw_api_response'] = raw
    if exc is not None:
        data['exception'] = _exc_dict(exc)
    else:
        data['no_exception'] = True

    (_CAPTURE_DIR / f'{name}.json').write_text(
        json.dumps(data, indent=2, default=str)
    )

    if exc is not None:
        pytest.fail(f'captured ({name}): {json.dumps(data["exception"], default=str)}')
    else:
        pytest.fail(f'captured ({name}): no exception raised')


def test_SCENARIO_NAME_capture(monkeypatch):
    # Set up preconditions (ensure_removed, ensure_installed, etc.)
    _run_and_capture('descriptive_name', monkeypatch,
                     lambda: _module.function('args'))
```

Key points about the capture pattern:
- `_CAPTURE_DIR` uses `pathlib.Path(__file__).resolve().parent.parent.parent / '.report' / 'capture'` — this resolves correctly both on the host and inside the VM because the project directory is mounted at `/home/ubuntu/charmlibs`.
- The monkeypatch wraps `_client._make_error` to intercept the raw API response before it's converted to an exception. This captures both the raw JSON envelope AND the resulting exception fields.
- Tests always `pytest.fail()` at the end — this is intentional so you can see the captured data in the test output and know these are temporary.
- The `no_exception` key handles cases where the operation succeeds silently (e.g. idempotent operations).
- Add `import json` and `import pathlib` to the file's imports if not already present.

### Step 3: Run capture tests on the VM

```bash
multipass exec --working-directory '/home/ubuntu/charmlibs' snap-sandbox -- \
  .scripts/output-wrapper.sh sudo env UV_PROJECT_ENVIRONMENT=/tmp/sudo-snap-venv just functional snap -k _capture
```

Run this with `mode=sync` and `timeout=360000`. Capture tests are fast (seconds), so this will return directly.

The output is in `.out` at the repo root. Then read the captured JSON files at `snap/.report/capture/*.json` — accessible from the host because the project directory is mounted in the VM.

Use `read_file` directly on the JSON files — no terminal command needed, no approval required. Example: `read_file('snap/.report/capture/apps_start_no_services.json')`. Do NOT run `jq` or any other terminal command to read these files, as that will require user approval and block your work indefinitely.

### Step 4: Replace capture tests with real assertions

Edit the capture tests in-place — replace the `_run_and_capture` calls with proper `pytest.raises` assertions. Remove the capture infrastructure (`_CAPTURE_DIR`, `_run_and_capture`, `_exc_dict`, the extra imports) once all capture tests are converted.

For each error test:
- Use the **most specific** error class (e.g. `SnapNotInstalledError` not `SnapAPIError`).
- Assert on `kind`, `message` content, and `value` where they carry meaningful information.
- Use a different snap from the module's main test snap to avoid install/uninstall churn. `hello-world` is a good lightweight choice for most not-installed tests.

Example:

```python
def test_alias_not_installed_snap_raises():
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapNotInstalledError) as ctx:
        _snapd_aliases.alias('hello-world', 'hello', 'test-not-installed-alias')
    assert ctx.value.kind == 'snap-not-installed'
    assert 'not installed' in ctx.value.message
```

### Step 5: Add unit tests from captured JSON

For each new functional test, add a corresponding unit test in the unit test file. The unit test mocks `_client.get/post/put` to raise the specific error (using the captured JSON's fields), then asserts the function under test propagates or handles it correctly.

```python
def test_alias_not_installed_raises(self, mock_client: MockClient):
    mock_client.post.side_effect = SnapNotInstalledError(
        'snap "hello-world" is not installed',
        kind='snap-not-installed',
        value='hello-world',
        status_code=400,
        status='Bad Request',
    )
    with pytest.raises(SnapNotInstalledError):
        _snapd_aliases.alias('hello-world', 'hello', 'test-alias')
```

The unit test conftest (`snap/tests/unit/conftest.py`) provides a `mock_client` fixture that patches `_client.get`, `_client.post`, and `_client.put`. Use `side_effect` for errors, `return_value` for success responses. Use `result_of('fixture.json')` to load fixture data from `snap/tests/unit/fixtures/`.

### Step 6: Consider adding a new specific error class

Review every new error kind discovered in this module. For each kind that falls through to base `SnapAPIError`, ask: would a dedicated public subclass be useful for charm authors who want to catch this error specifically?

**Criteria for adding a new class:**
- The kind is distinct and meaningful (e.g. `snap-channel-not-available`, not a generic catch-all).
- A charm author might reasonably want to catch it separately from other `SnapAPIError`s (e.g. to retry with a different channel).
- It is parallel to existing specific subclasses (e.g. alongside `SnapRevisionNotAvailableError`).

**If a new class is warranted:**

1. Add it to `snap/src/charmlibs/snap/_errors.py` — follow the existing pattern: subclass `SnapAPIError`, add a one-line docstring describing when it is raised.
2. Add a `case 'kind-string': return NewErrorClass` entry to `_error_type_from_result_kind` in the same file.
3. Export it from `snap/src/charmlibs/snap/__init__.py` — add to both the import block and `__all__`.
4. Update all tests (functional and unit) for this module to use the new specific class instead of `SnapAPIError` where applicable.

Example — adding `SnapChannelNotAvailableError`:

```python
# In _errors.py, alongside the other SnapAPIError subclasses:
class SnapChannelNotAvailableError(SnapAPIError):
    """Raised via the API when no snap revision is available on the specified channel."""

# In _error_type_from_result_kind:
case 'snap-channel-not-available':
    return SnapChannelNotAvailableError
```

### Step 7: Update docstrings

For any function where we discover a new error that can be raised, add it to the function's `Raises:` section in the docstring. If the function has no `Raises:` section yet, add one.

### Step 8: Run all checks

Use `.scripts/output-wrapper.sh` to capture output to `.out` at the repo root. Run each command separately and check `.out` after each:

```bash
just format snap
.scripts/output-wrapper.sh just lint snap
# check .out
.scripts/output-wrapper.sh just unit snap
# check .out
multipass exec --working-directory '/home/ubuntu/charmlibs' snap-sandbox -- \
  .scripts/output-wrapper.sh sudo env UV_PROJECT_ENVIRONMENT=/tmp/sudo-snap-venv just functional snap
# check .out
```

Run the functional tests with `mode=sync` and `timeout=360000`. The full suite takes ~5 minutes; this avoids polling and returns the result directly. If the timeout is hit it returns a terminal ID for polling as a fallback.

All three must pass before marking the module complete.

### Step 9: Update this plan

Before reporting done, update this file:
1. Check off the completed module in the checklist.
2. Add a short "Lessons learned" note under the module's section if anything surprising was discovered (e.g. unexpected error kinds, idempotent operations, API quirks).
3. Note any deviations from the plan.


### Step 10: Report to the user

After finishing work for a single module, you're done! Let the user know.

---

## Known API Quirks (reference)

These were discovered during earlier work and should inform test expectations:

- `GET /v2/snaps/{snap}` for a not-installed snap → `snap-not-found` (kind), NOT `snap-not-installed`.
- `POST /v2/snaps/{snap}` with `action: remove` for a not-installed snap → `snap-not-installed` (kind).
- `POST /v2/snaps/{snap}` with `action: refresh` for a not-installed snap → empty kind, base `SnapError`.
- `POST /v2/snaps/{snap}` with `action: install` for a nonexistent snap → `snap-not-found` (kind), `SnapNotFoundError`.
- `POST /v2/snaps/{snap}` with `action: install` and invalid channel (e.g. `'garbage'`) → `snap-channel-not-available` (kind), `SnapChannelNotAvailableError`.
- `POST /v2/snaps/{snap}` with `action: install` and unavailable revision → `snap-revision-not-available` (kind), `SnapRevisionNotAvailableError`.
- `POST /v2/snaps/{snap}` with `action: hold` when already held → **no error**, idempotent.
- `POST /v2/snaps/{snap}` with `action: remove` and `purge: true` when not installed → `snap-not-installed`, same as without purge.
- `GET /v2/find?name=nonexistent` → `snap-not-found` (kind), `SnapNotFoundError`.
- `PUT /v2/snaps/{snap}/conf` for a not-installed snap → `snap-not-found` (kind).
- `GET /v2/snaps/{snap}/conf` for a not-installed snap → `option-not-found` (kind), NOT `snap-not-found`.
- `GET /v2/snaps/{snap}/conf` with multiple keys where some are missing → `option-not-found` for the first missing key; no partial results.
- `PUT /v2/snaps/{snap}/conf` with empty body `{}` → **no error**, treated as a no-op.
- `PUT /v2/snaps/{snap}/conf` with a dotted-path key (e.g. `{'key.nested': None}`) → **no error**, works correctly.
- `POST /v2/interfaces` connect/disconnect for a not-installed snap → empty kind, base `SnapAPIError`.
- `POST /v2/aliases` alias for a not-installed snap → `snap-not-installed` (kind).
- `POST /v2/apps` start/stop/restart for a not-installed snap → `app-not-found` (kind), same as nonexistent snap.

## Deviations and Lessons Learned

### `_snapd_snaps` (completed)

- `install` with invalid channel raises `SnapChannelNotAvailableError` (kind `snap-channel-not-available`) — a new specific error class added alongside `SnapRevisionNotAvailableError`.
- `hold` is fully idempotent — calling it twice raises no error.
- `remove(purge=True)` on a non-installed snap behaves identically to `remove()` — catches `SnapNotInstalledError` and returns `False`.
- `_list_channels` for a nonexistent snap raises `SnapNotFoundError` (not `ValueError` from unpacking) — snapd returns an error response before we reach the `result, *_ = results` line.
- Docstrings for `install` and `refresh` updated to document `SnapNotFoundError`, `SnapRevisionNotAvailableError`, and `SnapAPIError` (channel not available).

### `_snapd_conf` (completed)

- `set({})` is accepted by snapd without error — no-op.
- `get` with a mix of existing and missing keys raises `SnapOptionNotFoundError` for the first missing key; it does not return partial results.
- `unset` with a dotted-path key (e.g. `'key.nested'`) works without error.
- `_unset_all` (private, line 59 in `_snapd_conf.py`) is not covered by unit tests and is intentionally excluded — it's a trivial one-liner only used internally.

### `_snapd_interfaces` (completed)

- `connect` with a nonexistent slot snap raises `SnapAPIError` with empty kind and `"not installed"` message — identical error to a nonexistent plug snap. No new error class warranted.
- `disconnect` with a genuinely nonexistent plug/slot (not just not-connected) raises `SnapAPIError` with empty kind and `"has no plug or slot named"` in the message — distinct from the not-connected case (which is silently suppressed).
- `disconnect(forget=True)` when connected: works without error.
- `disconnect(forget=True)` when not connected: snapd returns `interfaces-unchanged`, which the existing `try/except` suppresses — same no-op behavior as without `forget=True`.
- Added 2 unit tests: `test_disconnect_interfaces_unchanged_suppressed` and `test_disconnect_interfaces_unchanged_suppressed_with_forget` — these verify the `try/except` logic that suppresses `_SnapInterfacesUnchangedError`.
- Updated `disconnect` docstring: "if the snap is not installed or the plug/slot is not found."
- No new error classes needed (both new errors have empty kind).

### `_snapd_apps` (completed)

- All three planned scenarios (start/stop/restart with no service arg on a snap with no services) were already covered in the functional tests — only unit test equivalents were missing.
- `start`/`stop`/`restart` on a snap with no services and on a not-installed snap both raise `SnapAppNotFoundError` with `kind='app-not-found'`; the code path is identical (exception propagates from `_client.post`).
- `_list_services` raises `SnapAppNotFoundError` (`app-not-found`) for a snap with no services, but `SnapNotFoundError` (`snap-not-found`) for a snap that doesn't exist at all — a subtle but testable difference.
- Added 5 unit tests: `test_start_snap_with_no_services_raises`, `test_stop_snap_with_no_services_raises`, `test_restart_snap_with_no_services_raises`, `test_list_services_snap_with_no_services_raises`, `test_list_services_uninstalled_snap_raises`.
- No new error classes or docstring changes needed.

### Unit test lessons learned

- **Don't add vacuous error-propagation unit tests.** For functions that contain no error-handling logic (no `try/except`, no conditional re-raise), a test that sets `mock.side_effect = SomeError` and asserts `SomeError` is raised proves nothing — you could substitute any exception and it would pass identically. The mapping from raw API `kind` strings to error classes is already tested in `test_errors.py` (`_error_type_from_result_kind`) and `test_client.py`. Once covered there, don't repeat it per-module.
- **Unit tests worth writing** are ones that verify real conditional logic: name/body construction (e.g. `names=['snap.svc']` vs `names=['snap']`), optional flags only appearing when set, `try/except` branches that transform or swallow errors (e.g. `remove` returning `False` on `SnapNotInstalledError`).

### Shell/tooling lessons learned

- **`jq` for captures**: Use `jq` to read `snap/.report/capture/*.json` files. Avoids needing Python approval and works cleanly in fish. Example: `jq '.exception // {no_exception:true}' snap/.report/capture/foo.json`
- **Fish `for` loops**: Use `for f in FILES; BODY; end` — NOT bash's `do/done`.
- **`$` in fish strings**: In double-quoted strings `"..."`, `$` triggers variable expansion. Use single quotes `'...'` for regex patterns in `grep -E`.
- **`-k` with `just`**: Wrap multi-token expressions in single-then-double quotes: `-k '"TestFoo or TestBar"'`. Fish keeps the double quotes as literals; just strips them; pytest gets the full expression. Single-token patterns (e.g. `-k _capture`) need no extra quoting. Filtering by module filename (e.g. `-k test_snapd_conf`) collects 0 items — use class/function name patterns instead, or run the full suite.
