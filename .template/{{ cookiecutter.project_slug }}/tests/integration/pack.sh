#!/usr/bin/env bash
# This script is executed in this directory via `just pack-k8s` or `just pack-machine`.
# Extra args are passed to this script, e.g. `just pack-k8s foo` -> $1 is 'foo'.
# These commands are invoked in CI:
#     - if this file exists and `just integration-<substrate>` would execute any tests
#     - before running integration tests
#     - with no additional arguments
#
# Environment variables:
# $CHARMLIBS_SUBSTRATE will have the value 'k8s' or 'machine' (set by pack-k8s or pack-machine)
# in CI, $CHARMLIBS_TAG is set based on pyproject.toml:tools.charmlibs.integration.tags
#     set $CHARMLIBS_TAG locally for testing, or use the tag variable
#     e.g. just tag=24.04 pack-k8s some extra args
set -xueo pipefail

: copy charm files to temporary directory
TMPDIR=".tmp"
rm -rf "$TMPDIR"
cp --recursive --dereference "charms/$CHARMLIBS_SUBSTRATE/$CHARMLIBS_TAG/" "$TMPDIR"

: copy library code to temporary directory
mkdir "$TMPDIR/package"
cp --recursive --target-directory="$TMPDIR/package/" ../../src ../../pyproject.toml ../../README.md

: pack charm
cd "$TMPDIR"
uv lock  # required by uv charm plugin
charmcraft pack
cd -

: place packed charm in expected location
PACKED_DIR=".packed"
mkdir "$PACKED_DIR"
mv "$TMPDIR"/*.charm "$PACKED_DIR/$CHARMLIBS_SUBSTRATE.charm"  # read in conftest.py