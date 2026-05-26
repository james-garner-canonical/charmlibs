If this file is in context and work is on the snap library, treat it with the same importance as AGENTS.md at the repo root.

Familiarise yourself with the codebase by reading everything under snap/src.

Always run these checks. Redirect output to `snap/.report/` so that verbose output doesn't flood your context — read the log file selectively (e.g. with `grep` or `tail`) only if a command fails:
```
mkdir -p snap/.report
just lint snap > snap/.report/lint.log 2>&1 && echo "lint passed" || tail -50 snap/.report/lint.log
just format snap  # fix any formatting issues (prints a diff if changes are needed; no redirect needed)
just unit snap > snap/.report/unit.log 2>&1 && echo "unit passed" || grep -E "FAILED|ERROR|short test summary" snap/.report/unit.log | head -50
```
Also run tests against the real snapd API like this if the change is substantial, and before reporting completion. These are a bit slow so run them less frequently than the unit tests. Select specific tests with `-k '<expression>'`.
```
multipass exec --working-directory '/home/ubuntu/charmlibs' snap-sandbox -- sudo env UV_PROJECT_ENVIRONMENT=/tmp/sudo-snap-venv just functional snap > snap/.report/functional.log 2>&1 && echo "functional passed" || tail -80 snap/.report/functional.log
```
If the VM isn't available, you must either stop and ask the user, or proceed without functional tests (only if appropriate).
IMPORTANT: Always use the `--working-directory` and `UV_PROJECT_ENVIRONMENT` arguments, or else there is big trouble.

Read the `justfile` if you ever need to see what these commands actually do. You can search for lines starting with the recipe name.

Before you make any changes, run all these checks to make sure there aren't any preexisting issues. If there are, identify them and suggest fixes before proceeding further.

---

If you need to check how the API responds, you can run commands like this:
```
multipass exec --working-directory '/home/ubuntu/charmlibs' snap-sandbox -- sudo uvx --with-editable ./snap python -c 'from charmlibs.snap import _client; print(_client.put("/v2/snaps/<snap>/conf", body={}))'
```
```
multipass exec --working-directory '/home/ubuntu/charmlibs' snap-sandbox -- sudo curl -s --unix-socket /run/snapd.socket http://localhost/v2/logs?names=<snap>&n=1
```
```
multipass exec snap-sandbox -- sudo curl -sS -X POST --unix-socket /run/snapd.socket \
  -H "Content-Type: application/json" \
  -d '{"action": "install", "revision": "7836"}' \
  http://localhost/v2/snaps/firefox
```
