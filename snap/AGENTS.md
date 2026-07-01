If this file is in context and work is on the snap library, treat it with the same importance as AGENTS.md at the repo root.

## Running checks

Always run these checks before reporting completion:
```
just format snap
just lint snap
just unit snap
```
If the change is substantial run tests against the real snapd API in a workshop container:
```
workshop exec resolute -- sudo just functional snap
```
If workshop isn't launched yet, run `workshop launch resolute` first. The full test suite takes around 5 minutes. Select specific tests with `-k '<expression>'`.

## Checking the snapd API directly

This library is closely coupled to the snapd API. Query the API in the workshop container to check its behaviour. The repository root is mounted in the container, so you can write scripts in the repository and execute them in the container. Likewise, files written to the repository directory in the container are available locally for inspection. For example:

```python
# script.py
import json
from charmlibs.snap import _client

result = _client.put('/v2/snaps/<snap>/conf', body={})
with open('out.json', 'w') as f:
    json.dump(result, f, indent=2, default=str)
```

Run it with `workshop exec`:
```bash
workshop exec resolute -- sudo uvx --with-editable ./snap python script.py
```

You can also use curl directly for quick checks:
```
workshop exec resolute -- sudo curl -s --unix-socket /run/snapd.socket http://localhost/v2/logs?names=<snap>&n=1
```

For interactive exploration, use `workshop shell resolute`.

---

## Strategy for adding tests (capture-then-assert)

When adding functional and unit tests — especially for error paths — follow this capture-then-assert workflow. Do NOT guess what errors the snapd API returns; always discover them empirically first.

### Step 1: Write exploratory capture tests

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
- `_CAPTURE_DIR` uses `pathlib.Path(__file__).resolve().parent.parent.parent / '.report' / 'capture'` — this resolves correctly both on the host and inside the workshop container because the project directory is mounted at `/project`.
- The monkeypatch wraps `_client._make_error` to intercept the raw API response before it's converted to an exception. This captures both the raw JSON envelope AND the resulting exception fields.
- Tests always `pytest.fail()` at the end — this is intentional so you can see the captured data in the test output and know these are temporary.
- The `no_exception` key handles cases where the operation succeeds silently (e.g. idempotent operations).
- Add `import json` and `import pathlib` to the file's imports if not already present.

### Step 2: Run capture tests

```bash
workshop run resolute -- functional snap -k _capture
```

Run this with `mode=sync` and `timeout=360000`.

The output is in `.out` at the repo root. Then read the captured JSON files at `snap/.report/capture/*.json` — accessible from the host because the project directory is mounted in the workshop container.

Use `read_file` directly on the JSON files — no terminal command needed, no approval required. Do NOT run `jq` or any other terminal command to read these files.

### Step 3: Replace capture tests with real assertions

Edit the capture tests in-place — replace the `_run_and_capture` calls with proper `pytest.raises` assertions. Remove the capture infrastructure (`_CAPTURE_DIR`, `_run_and_capture`, `_exc_dict`, the extra imports) once all capture tests are converted.

For each error test:
- Use the **most specific** error class (e.g. `NotInstalledError` not `APIError`).
- Assert on `kind`, `message` content, and `value` where they carry meaningful information.
- Use a different snap from the module's main test snap to avoid install/uninstall churn. `hello-world` is a good lightweight choice for most not-installed tests.

Example:

```python
def test_alias_not_installed_snap_raises():
    ensure_removed('hello-world')
    with pytest.raises(_errors.NotInstalledError) as ctx:
        _snapd_aliases.alias('hello-world', 'hello', 'test-not-installed-alias')
    assert ctx.value.kind == 'snap-not-installed'
    assert 'not installed' in ctx.value.message
```

### Step 4: Add unit tests from captured JSON

For each new functional test, add a corresponding unit test in the unit test file. The unit test mocks `_client.get/post/put` to raise the specific error (using the captured JSON's fields), then asserts the function under test propagates or handles it correctly.

The unit test conftest (`snap/tests/unit/conftest.py`) provides a `mock_client` fixture that patches `_client.get`, `_client.post`, and `_client.put`. Use `side_effect` for errors, `return_value` for success responses. Use `result_of('fixture.json')` to load fixture data from `snap/tests/unit/fixtures/`.

```python
def test_alias_not_installed_raises(self, mock_client: MockClient):
    mock_client.post.side_effect = NotInstalledError(
        'snap "hello-world" is not installed',
        kind='snap-not-installed',
        value='hello-world',
        status_code=400,
        status='Bad Request',
    )
    with pytest.raises(NotInstalledError):
        _snapd_aliases.alias('hello-world', 'hello', 'test-alias')
```

### Step 5: Consider adding new error classes

Review every new error kind discovered. For each kind that falls through to base `APIError`, ask: would a dedicated public subclass be useful for charm authors who want to catch this error specifically?

**Criteria for adding a new class:**
- The kind is distinct and meaningful (e.g. `snap-channel-not-available`, not a generic catch-all).
- A charm author might reasonably want to catch it separately from other `APIError`s.
- It is parallel to existing specific subclasses.

**If a new class is warranted:**

1. Add it to `snap/src/charmlibs/snap/_errors.py` — subclass `APIError`, one-line docstring.
2. Add a `case 'kind-string': return NewErrorClass` entry to `_error_type_from_result_kind` in the same file.
3. Export it from `snap/src/charmlibs/snap/__init__.py` — add to both the import block and `__all__`.
4. Update all tests to use the new specific class instead of `APIError` where applicable.

### Step 6: Update docstrings

For any function where a new raisable error was discovered, add it to the function's `Raises:` section. If the function has no `Raises:` section yet, add one.

### Step 7: Run all checks

```bash
just format snap
just lint snap
just unit snap
workshop run resolute -- functional snap
```

All three must pass before reporting completion.
