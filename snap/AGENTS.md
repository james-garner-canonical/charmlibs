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

## Strategy for adding tests (capture-then-assert)

**Never guess what the snapd API returns.** Always capture real responses first, then write assertions against them. This applies to both error paths and success responses.

1. **Capture**: Run the real API call in a workshop container and record the raw response (and/or the resulting exception). A simple way is a throwaway script using `_client` directly, or a temporary functional test that dumps the response to a JSON file.
2. **Assert**: Replace the capture with real assertions using the captured data — the most specific error class, `kind`, `message`, and `value`.
3. **Mirror in unit tests**: Add a unit test that mocks `_client` to raise/return the captured response and asserts the function under test handles it correctly.
4. **Consider new error classes**: If a captured `kind` falls through to base `APIError` and a charm author might reasonably want to catch it specifically, add a dedicated subclass in `_errors.py`, wire it into `_error_type_from_result_kind`, and export it from `__init__.py`.
5. **Update docstrings**: Add any newly-discovered raisable errors to the function's `Raises:` section.
