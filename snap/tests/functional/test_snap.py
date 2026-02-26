#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.


import datetime
import logging
import sys
from subprocess import CalledProcessError, check_output

import pytest

from charmlibs import snap

# enable debug logging from snap library during tests
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
snap_logger = logging.getLogger(snap.__name__)
snap_logger.setLevel(logging.DEBUG)
snap_logger.addHandler(handler)


def get_command_path(command: str) -> str:
    try:
        return check_output(['which', command]).decode().strip()
    except CalledProcessError:
        return ''


def test_snap_install():
    # # Try by initialising the cache first, then using ensure
    # try:
    #     cache = snap.SnapCache()
    #     juju = cache['juju']
    #     if not juju.present:
    #         juju.ensure(snap.SnapState.Latest, channel='stable')
    # except snap.SnapError as e:
    #     logger.error('An exception occurred when installing Juju. Reason: %s', e.message)
    snap.install('juju')
    assert get_command_path('juju') == '/snap/bin/juju'


# redundant
# def test_snap_install_bare():
#     # snap.add(['charmcraft'], state=snap.SnapState.Latest, classic=True, channel='candidate')
#     snap.install('charmcraft', channel='latest/candidate', classic=True)
#     assert get_command_path('charmcraft') == '/snap/bin/charmcraft'


def test_snap_remove():
    # # First ensure that charmcraft is installed
    # # (it might be if this is run after the install test)
    # cache = snap.SnapCache()
    # charmcraft = cache['charmcraft']
    # if not charmcraft.present:
    #     charmcraft.ensure(snap.SnapState.Latest, classic=True, channel='candidate')
    snap.ensure('charmcraft', classic=True)
    assert get_command_path('charmcraft') == '/snap/bin/charmcraft'
    snap.remove('charmcraft')
    assert get_command_path('charmcraft') == ''


def test_snap_refresh():
    # cache = snap.SnapCache()
    # hello_world = cache['hello-world']
    # if not hello_world.present:
    #     hello_world.ensure(snap.SnapState.Latest, channel='latest/stable')
    # cache = snap.SnapCache()
    # hello_world = cache['hello-world']
    # assert hello_world.channel == 'latest/stable'
    snap.ensure('hello-world', channel='latest/stable')
    assert snap.info('hello-world').channel == 'latest/stable'
    # hello_world.ensure(snap.SnapState.Latest, channel='latest/candidate')
    # # Refresh cache
    # cache = snap.SnapCache()
    # hello_world = cache['hello-world']
    # assert hello_world.channel == 'latest/candidate'
    snap.ensure('hello-world', channel='latest/candidate')
    assert snap.info('hello-world').channel == 'latest/candidate'


def test_snap_set_and_get_with_typed():
    # cache = snap.SnapCache()
    # lxd = cache['lxd']

    # def try_ensure_snap(retries: int) -> None:
    #     try:
    #         lxd.ensure(snap.SnapState.Latest, channel='latest')
    #     except snap.SnapError:
    #         if retries <= 0:
    #             raise
    #         time.sleep(20)
    #         try_ensure_snap(retries=retries - 1)

    # try_ensure_snap(retries=10)

    configs = {
        'true': True,
        'false': False,
        'null': None,
        'integer': 1,
        'float': 2.0,
        'list': [1, 2.0, True, False, None],
        'dict': {
            'true': True,
            'false': False,
            'null': None,
            'integer': 1,
            'float': 2.0,
            'list': [1, 2.0, True, False, None],
        },
        'criu.enable': 'true',
        'ceph.external': 'false',
    }

    # lxd.set(configs, typed=True)

    snap.ensure('lxd')
    snap.set('lxd', configs)

    lxd = snap.get('lxd')
    assert lxd

    assert lxd.get('true') is True
    assert lxd.get('false') is False
    assert 'null' not in lxd
    assert lxd['integer'] == 1
    assert lxd['float'] == 2.0
    assert lxd['list'] == [1, 2.0, True, False, None]

    # Note that `"null": None` will be missing here because `key=null` will not
    # be set (because it means unset in snap). However, `key=[null]` will be
    # okay, and that's why `None` exists in "list".
    assert lxd['dict'] == {
        'true': True,
        'false': False,
        'integer': 1,
        'float': 2.0,
        'list': [1, 2.0, True, False, None],
    }

    assert snap.get_one('lxd', 'dict.true') is True
    assert snap.get_one('lxd', 'dict.false') is False
    with pytest.raises(snap.SnapError):
        snap.get_one('lxd', 'dict.null')
    assert snap.get_one('lxd', 'dict.integer') == 1
    assert snap.get_one('lxd', 'dict.float') == 2.0
    assert snap.get_one('lxd', 'dict.list') == [1, 2.0, True, False, None]

    assert snap.get_one('lxd', 'criu.enable') == 'true'
    assert snap.get_one('lxd', 'ceph.external') == 'false'


# def test_snap_set_and_get_untyped():
#     cache = snap.SnapCache()
#     lxd = cache['lxd']
#     try:
#         lxd.ensure(snap.SnapState.Latest, channel='latest')
#     except snap.SnapError:
#         time.sleep(60)
#         lxd.ensure(snap.SnapState.Latest, channel='latest')
#
#     lxd.set({'foo': 'true', 'bar': True}, typed=False)
#     assert lxd.get('foo', typed=False) == 'true'
#     assert lxd.get('bar', typed=False) == 'True'


def test_unset_key_raises_snap_error():
    # cache = snap.SnapCache()
    # lxd = cache['lxd']
    # lxd.ensure(snap.SnapState.Latest, channel='latest')

    snap.ensure('lxd')
    # Verify that the correct exception gets raised in the case of an unset key.
    key = 'keythatdoesntexist01'
    with pytest.raises(snap.SnapError) as ctx:
        snap.get('lxd', key)
    assert key in ctx.value.message

    # FIXME: We should probably continue to offer this functionality as it was requested recently.
    # but I don't think we should be including the latest logs in the error message by default,
    # since it can be very expensive to retrieve them and is not usually relevant to the error.
    # Maybe we could use an env var, require an option, or have a separate method
    # for retrieving logs explicitly that charms can use in error cases.

    # assert '\nLatest logs:\n' in ctx.value.message  # journalctl log retrieval on SnapError

    # # We can make the above work w/ arbitrary config.
    # lxd.set({key: 'true'})
    # assert lxd.get(key) == 'true'
    snap.set('lxd', {key: 'true'})
    assert snap.get_one('lxd', key) == 'true'


def test_snap_ensure():
    # cache = snap.SnapCache()
    # charmcraft = cache['charmcraft']

    # # Verify that we can run ensure multiple times in a row without delays.
    # charmcraft.ensure(snap.SnapState.Latest, channel='latest/stable')
    # charmcraft.ensure(snap.SnapState.Latest, channel='latest/stable')
    # charmcraft.ensure(snap.SnapState.Latest, channel='latest/stable')

    snap.ensure('charmcraft', classic=True)
    did_something = snap.ensure('charmcraft', classic=True)
    assert not did_something
    with pytest.raises(ValueError):
        snap.ensure('charmcraft')  # classic=False
    did_something = snap.ensure('charmcraft', classic=True)
    assert not did_something


def test_new_snap_ensure():
    # vlc = snap.SnapCache()['vlc']
    # vlc.ensure(snap.SnapState.Latest, channel='edge')
    snap.ensure('vlc', channel='edge')


def test_snap_ensure_revision():
    # juju = snap.SnapCache()['juju']

    # # Verify that the snap is not installed
    # juju.ensure(snap.SnapState.Available)
    # assert get_command_path('juju') == ''

    snap.remove('juju', missing_ok=True)

    # # Install the snap with the revision of latest/edge
    # snap_info_juju = run(
    #     ['snap', 'info', 'juju'], capture_output=True, encoding='utf-8'
    # ).stdout.split('\n')

    # edge_version = None
    # edge_revision = None
    # for line in snap_info_juju:
    #     match = re.search(r'3/stable:\s+([^\s]+).+\((\d+)\)', line)

    #     if match:
    #         edge_version = match.group(1)
    #         edge_revision = match.group(2)
    #         break
    # assert edge_revision is not None

    channels = snap.channels('juju')
    info = channels['3/stable']
    snap.install('juju', revision=info.revision)

    # juju.ensure(snap.SnapState.Present, revision=edge_revision)

    assert get_command_path('juju') == '/snap/bin/juju'

    # snap_info_juju = run(
    #     ['snap', 'info', 'juju'],
    #     capture_output=True,
    #     encoding='utf-8',
    # ).stdout.strip()

    # assert 'installed' in snap_info_juju
    # for line in snap_info_juju.split('\n'):
    #     if 'installed' in line:
    #         match = re.search(r'installed:\s+([^\s]+).+\((\d+)\)', line)

    #         assert match is not None
    #         assert match.group(1) == edge_version
    #         assert match.group(2) == edge_revision

    # assert juju.version == edge_version

    info = snap.info('juju')
    assert info.revision == info.revision


def test_snap_start():
    # cache = snap.SnapCache()
    # kp = cache['kube-proxy']
    # kp.ensure(snap.SnapState.Latest, classic=True, channel='latest/stable')

    snap.ensure('kube-proxy', classic=True, channel='latest/stable')
    services = snap._snap.list_services('kube-proxy')
    assert services
    daemon = next(s for s in services if s['name'] == 'daemon')
    assert daemon.get('active')

    # assert kp.services
    # kp.start()
    # assert kp.services['daemon']['active'] is not False

    snap.services_stop('kube-proxy', 'daemon')
    services = snap._snap.list_services('kube-proxy')
    assert services
    daemon = next(s for s in services if s['name'] == 'daemon')
    assert not daemon.get('active')

    snap.services_start('kube-proxy', 'daemon')
    services = snap._snap.list_services('kube-proxy')
    assert services
    daemon = next(s for s in services if s['name'] == 'daemon')
    assert daemon['active']

    with pytest.raises(snap.SnapError):
        # kp.start(['foobar'])
        snap.services_start('kube-proxy', 'foobar')


def test_snap_stop():
    # cache = snap.SnapCache()
    # kp = cache['kube-proxy']
    # kp.ensure(snap.SnapState.Latest, classic=True, channel='latest/stable')

    snap.ensure('kube-proxy', classic=True, channel='latest/stable')

    # kp.stop(['daemon'], disable=True)
    # assert kp.services['daemon']['active'] is False
    # assert kp.services['daemon']['enabled'] is False

    snap.services_stop('kube-proxy', 'daemon', disable=True)
    services = snap._snap.list_services('kube-proxy')
    daemon = next(s for s in services if s['name'] == 'daemon')
    assert not daemon.get('active')
    assert not daemon.get('enabled')


def test_snap_logs():
    # cache = snap.SnapCache()
    # kp = cache['kube-proxy']
    # kp.ensure(snap.SnapState.Latest, classic=True, channel='latest/stable')

    snap.ensure('kube-proxy', classic=True, channel='latest/stable')

    # Terrible means of populating logs
    # kp.start()
    # kp.stop()
    # kp.start()
    # kp.stop()

    before = snap._snap.logs('kube-proxy', num_lines=10)

    snap.services_start('kube-proxy')
    snap.services_stop('kube-proxy')
    snap.services_start('kube-proxy')
    snap.services_stop('kube-proxy')

    # assert len(kp.logs(num_lines=15).splitlines()) >= 4

    after = snap._snap.logs('kube-proxy', num_lines=10)
    assert len(before) == 10 or len(after) > len(before)


def test_snap_restart():
    # cache = snap.SnapCache()
    # kp = cache['kube-proxy']
    # kp.ensure(snap.SnapState.Latest, classic=True, channel='latest/stable')

    # try:
    #     kp.restart()
    # except CalledProcessError as e:
    #     pytest.fail(e.stderr)

    snap.ensure('kube-proxy', classic=True, channel='latest/stable')
    snap.services_restart('kube-proxy')


def test_snap_hold_refresh():
    # cache = snap.SnapCache()
    # hw = cache['hello-world']
    # hw.ensure(snap.SnapState.Latest, channel='latest/stable')

    snap.ensure('hello-world', channel='latest/stable')

    # hw.hold(duration=timedelta(hours=24))
    # assert hw.held

    snap.hold('hello-world', duration=datetime.timedelta(days=2))
    info = snap.info('hello-world')
    assert info.hold is not None
    if sys.version_info >= (3, 11):
        hold = datetime.datetime.fromisoformat(info.hold)
    else:
        # Python 3.10 can't parse the fractional seconds with fromisoformat.
        # We parse the format manually here for Ubuntu 22.04 tests.
        #
        # The snapd version that comes with Ubuntu 22.04 emits Z-suffixed timestamps.
        # Newer snapd versions emit RFC3339 timestamps with timezone offsets, but we don't
        # need to handle them here since they're covered by fromisoformat in Python 3.11+.
        dt, ms = info.hold.removesuffix('Z').split('.')
        hold = datetime.datetime.fromisoformat(dt).astimezone() + datetime.timedelta(
            microseconds=int(ms[:6])
        )
    assert hold - datetime.datetime.now().astimezone() > datetime.timedelta(days=1)


def test_snap_unhold_refresh():
    # cache = snap.SnapCache()
    # hw = cache['hello-world']
    # hw.ensure(snap.SnapState.Latest, channel='latest/stable')

    snap.ensure('hello-world', channel='latest/stable')

    # hw.unhold()
    # assert not hw.held

    snap.unhold('hello-world')
    info = snap.info('hello-world')
    assert info.hold is None


def test_snap_connect():
    # cache = snap.SnapCache()
    # vlc = cache['vlc']
    # vlc.ensure(snap.SnapState.Latest, classic=True, channel='latest/stable')

    snap.ensure('vlc')

    # try:
    #     vlc.connect('jack1')
    # except CalledProcessError as e:
    #     pytest.fail(e.stderr)

    snap.connect('vlc', 'mount-observe')


# we don't plan to implement global hold refresh
#
# def test_hold_refresh():
#     hold_date = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')
#     snap.hold_refresh()
#     result = check_output(['snap', 'refresh', '--time'])
#     assert f'hold: {hold_date}' in result.decode()
#
#
# def test_forever_hold_refresh():
#     snap.hold_refresh(forever=True)
#     result = check_output(['snap', 'get', 'system', 'refresh.hold'])
#     assert 'forever' in result.decode()
#
#
# def test_reset_hold_refresh():
#     snap.hold_refresh()
#     snap.hold_refresh(0)
#     result = check_output(['snap', 'refresh', '--time'])
#     assert 'hold: ' not in result.decode()


def test_alias():
    # cache = snap.SnapCache()
    # lxd = cache['lxd']

    snap.ensure('lxd')
    snap.alias('lxd', 'lxc', 'testlxc')

    result = check_output(['snap', 'aliases'], text=True)
    found = any(line.split() == ['lxd.lxc', 'testlxc', 'manual'] for line in result.splitlines())
    assert found, result
