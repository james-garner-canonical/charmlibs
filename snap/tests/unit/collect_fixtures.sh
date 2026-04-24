#!/usr/bin/env bash
# Replace synthesized fixtures with real snapd API responses from snap-sandbox VM.
# Run from repo root: bash snap/tests/unit/collect_fixtures.sh
set -xeuo pipefail
FIXTURES="snap/tests/unit/fixtures"
mkdir -p "$FIXTURES"
CURL="multipass exec --no-map-working-directory snap-sandbox -- sudo curl -sS --unix-socket /run/snapd.socket"

wait_change() {
    local id=$1
    for _ in $(seq 1 60); do
        local s
        s=$($CURL "http://localhost/v2/changes/$id" \
            | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['status'])")
        case "$s" in Done|Error|Wait) return 0 ;; esac
        sleep 1
    done
    echo "Timeout on change $id" >&2; return 1
}

post() {
    local ep=$1 body=$2
    multipass exec --no-map-working-directory snap-sandbox -- sudo curl -sS --unix-socket /run/snapd.socket \
        -X POST -H 'Content-Type: application/json' -d "$body" "http://localhost$ep"
}

get_change_id() {
    python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('change',''))"
}

# Phase 1: read-only
echo "Phase 1: read-only queries..."
$CURL http://localhost/v2/snaps/hello-world | python3 -m json.tool > "$FIXTURES/snap_info_hello_world.json"
$CURL http://localhost/v2/snaps/kube-proxy  | python3 -m json.tool > "$FIXTURES/snap_info_kube_proxy.json"
$CURL "http://localhost/v2/snaps/lxd/conf"  | python3 -m json.tool > "$FIXTURES/conf_lxd_all.json"
$CURL "http://localhost/v2/snaps/lxd/conf?keys=core.https_address" | python3 -m json.tool > "$FIXTURES/conf_lxd_single_key.json"
$CURL "http://localhost/v2/snaps/lxd/conf?keys=keydoesnotexist01" | python3 -m json.tool > "$FIXTURES/conf_option_not_found_error.json"
$CURL "http://localhost/v2/apps?select=service&names=lxd"         | python3 -m json.tool > "$FIXTURES/services_lxd.json"
$CURL "http://localhost/v2/interfaces?select=all&plugs=true&slots=true" | python3 -m json.tool > "$FIXTURES/interfaces_all.json"
$CURL "http://localhost/v2/aliases"                               | python3 -m json.tool > "$FIXTURES/aliases_empty.json"

echo "  Collecting logs (raw stream)..."
$CURL "http://localhost/v2/logs?n=10&names=lxd" > "$FIXTURES/logs_lxd_raw.bin"
python3 -c "
import json, pathlib
data = pathlib.Path('$FIXTURES/logs_lxd_raw.bin').read_bytes()
entries = [json.loads(s) for line in data.split(b'\n\x1e') if (s := line.decode().strip())]
print(json.dumps(entries, indent=4))
" > "$FIXTURES/logs_lxd.json"

echo "  Collecting app-not-found log error (raw stream)..."
$CURL "http://localhost/v2/logs?n=10&names=hello-world" > "$FIXTURES/app_not_found_raw.bin"

# Phase 2: error cases (no state change)
echo "Phase 2: error cases..."
post /v2/snaps/hello-world '{"action":"install"}' | python3 -m json.tool > "$FIXTURES/snap_already_installed_error.json"
post /v2/snaps/hello-world '{"action":"refresh"}' | python3 -m json.tool > "$FIXTURES/snap_no_update_available_error.json"

echo "  snap-needs-classic: removing 'just' temporarily..."
RESP=$(post /v2/snaps/just '{"action":"remove"}')
CHANGE=$(echo "$RESP" | get_change_id)
[ -n "$CHANGE" ] && wait_change "$CHANGE"
post /v2/snaps/just '{"action":"install"}' | python3 -m json.tool > "$FIXTURES/snap_needs_classic_error.json"
echo "  Reinstalling 'just' with classic=true..."
RESP=$(post /v2/snaps/just '{"action":"install","classic":true}')
CHANGE=$(echo "$RESP" | get_change_id)
[ -n "$CHANGE" ] && wait_change "$CHANGE"

# Phase 3: hold → capture held info
echo "Phase 3: hold/unhold to capture held snap info..."
RESP=$(post /v2/snaps/hello-world '{"action":"hold","hold-level":"general","time":"forever"}')
CHANGE=$(echo "$RESP" | get_change_id)
[ -n "$CHANGE" ] && wait_change "$CHANGE"
$CURL http://localhost/v2/snaps/hello-world | python3 -m json.tool > "$FIXTURES/snap_info_hello_world_held.json"
RESP=$(post /v2/snaps/hello-world '{"action":"unhold"}')
CHANGE=$(echo "$RESP" | get_change_id)
[ -n "$CHANGE" ] && wait_change "$CHANGE"

# Phase 4: alias → capture with_entry
echo "Phase 4: alias/unalias to capture aliases list..."
RESP=$(post /v2/aliases '{"action":"alias","snap":"lxd","app":"lxc","alias":"testlxc"}')
CHANGE=$(echo "$RESP" | get_change_id)
[ -n "$CHANGE" ] && wait_change "$CHANGE"
$CURL "http://localhost/v2/aliases" | python3 -m json.tool > "$FIXTURES/aliases_with_entry.json"
RESP=$(post /v2/aliases '{"action":"unalias","alias":"testlxc"}')
CHANGE=$(echo "$RESP" | get_change_id)
[ -n "$CHANGE" ] && wait_change "$CHANGE"

echo ""
echo "Done. Fixtures written to $FIXTURES/"
echo ""
echo "MANUAL STEP: app_not_found_raw.bin is a \x1e-separated stream with a single error JSON object."
echo "Inspect it and save the JSON as $FIXTURES/app_not_found_error.json, e.g.:"
echo "  python3 -c \""
echo "    import json, pathlib"
echo "    data = pathlib.Path('$FIXTURES/app_not_found_raw.bin').read_bytes()"
echo "    obj = next(json.loads(s) for line in data.split(b'\\\n\\\x1e') if (s := line.decode().strip()))"
echo "    print(json.dumps(obj, indent=4))"
echo "  \" > $FIXTURES/app_not_found_error.json"
