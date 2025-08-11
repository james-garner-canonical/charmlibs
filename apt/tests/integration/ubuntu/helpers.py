# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

from subprocess import CalledProcessError, check_output


def get_command_path(command: str) -> str:
    try:
        return check_output(['which', command]).decode().strip()
    except CalledProcessError:
        return ''
