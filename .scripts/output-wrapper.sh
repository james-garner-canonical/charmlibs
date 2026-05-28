#!/usr/bin/env bash
# Run a command, capturing stdout and stderr to .out.
set -euo pipefail
"$@" > .out 2>&1
