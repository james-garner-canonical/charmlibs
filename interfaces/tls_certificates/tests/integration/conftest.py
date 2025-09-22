# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import jubilant
import pytest


@pytest.fixture(scope='session', autouse=True)
def jubi(request: pytest.FixtureRequest):
    yield
    if request.session.testsfailed:
        log = jubilant.Juju().debug_log(limit=1000)
        print(log, end='')


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        '--no-upgrade', action='store_true', default=False, help='do not run upgrade tests'
    )


# Adapted from
# https://docs.pytest.org/en/latest/example/simple.html#control-skipping-of-tests-according-to-command-line-option
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if True:  # if config.getoption('--no-upgrade'):  # FIXME: remove if True once lib is published
        skip_upgrade = pytest.mark.skip(reason='--no-upgrade option was given')
        for item in items:
            if 'upgrade' in item.keywords:
                item.add_marker(skip_upgrade)
