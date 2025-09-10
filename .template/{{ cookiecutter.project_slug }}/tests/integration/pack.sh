#!/usr/bin/env bash
# This script is executed in this directory via `just pack-k8s` or `just pack-machine`.
# Extra args are passed to this script, e.g. `just pack-k8s foo` -> $1 is 'foo'.
# In CI, the `just pack-<substrate>` commands are invoked:
#     - If this file exists and `just integration-<substrate>` would execute any tests
#     - Before running integration tests
#     - With no additional arguments
#
# Environment variables:
# $CHARMLIBS_SUBSTRATE will have the value 'k8s' or 'machine' (set by pack-k8s or pack-machine)
# In CI, $CHARMLIBS_TAG is set based on pyproject.toml:tool.charmlibs.integration.tags
# For local testing, set $CHARMLIBS_TAG directly or use the tag variable. For example:
# just tag=24.04 pack-k8s some extra args
set -xueo pipefail

: copy charm files to temporary directory for packing, dereferencing symlinks
TMPDIR=".tmp"
rm -rf "$TMPDIR"
cp --recursive --dereference "charms/$CHARMLIBS_SUBSTRATE/" "$TMPDIR"

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
mkdir -p "$PACKED_DIR"
mv "$TMPDIR"/*.charm "$PACKED_DIR/$CHARMLIBS_SUBSTRATE.charm"  # read in conftest.py
