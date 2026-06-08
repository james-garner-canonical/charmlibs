#!/usr/bin/env bash

# Source a functional-test package's setup.sh/teardown.sh around a command, in a single shell.
#
# Why this exists: setup.sh/teardown.sh must be *sourced* (not executed) by one long-lived shell --
# they export environment variables, set the umask, and start/stop background processes (e.g.
# pebble) whose lifetime has to span the whole command. That can't be reproduced from Python
# without re-implementing a shell, so this stays as the one small piece of bash.
#
# Usage: run with the working directory set to the package directory; "$@" is the command to run.

set -ueo pipefail
if [ -e tests/functional/setup.sh ]; then
    source ./tests/functional/setup.sh
fi
set +e
"$@"
returncode=$?
set -e
if [ -e tests/functional/teardown.sh ]; then
    source ./tests/functional/teardown.sh
fi
exit "$returncode"
