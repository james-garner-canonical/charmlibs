#!/usr/bin/env bash

# Source a package's functional test setup.sh/teardown.sh around a command.
# Usage: run with the working directory set to the package directory; "$@" is the command to run.
# Example: _functional.sh pytest tests/functional

set -xueo pipefail
if [ -e tests/functional/setup.sh ]; then
    source ./tests/functional/setup.sh
fi
set +e  # Allow the command to fail.
"$@"
returncode=$?
set -e  # Exit on error again.
if [ -e tests/functional/teardown.sh ]; then
    source ./tests/functional/teardown.sh
fi
exit "$returncode"
