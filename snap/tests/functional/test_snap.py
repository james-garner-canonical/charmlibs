#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.


import datetime
import logging
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
    snap.install('juju')
    assert get_command_path('juju') == '/snap/bin/juju'


def test_snap_remove():
    snap.ensure('charmcraft', classic=True)
    assert get_command_path('charmcraft') == '/snap/bin/charmcraft'
    snap.remove('charmcraft')
    assert get_command_path('charmcraft') == ''


def test_snap_refresh():
    snap.ensure('hello-world', channel='latest/stable')
    assert snap.info('hello-world').channel == 'latest/stable'

    snap.ensure('hello-world', channel='latest/candidate')
    assert snap.info('hello-world').channel == 'latest/candidate'


def test_snap_set_and_get_with_typed():
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

    assert snap._snapd._get_one('lxd', 'dict.true') is True
    assert snap._snapd._get_one('lxd', 'dict.false') is False
    with pytest.raises(snap.SnapError):
        snap._snapd._get_one('lxd', 'dict.null')
    assert snap._snapd._get_one('lxd', 'dict.integer') == 1
    assert snap._snapd._get_one('lxd', 'dict.float') == 2.0
    assert snap._snapd._get_one('lxd', 'dict.list') == [1, 2.0, True, False, None]

    assert snap._snapd._get_one('lxd', 'criu.enable') == 'true'
    assert snap._snapd._get_one('lxd', 'ceph.external') == 'false'


def test_unset_key_raises_snap_error():
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

    # We can make the above work w/ arbitrary config.
    snap.set('lxd', {key: 'true'})
    assert snap._snapd._get_one('lxd', key) == 'true'


def test_snap_ensure():
    snap.ensure('charmcraft', classic=True)
    did_something = snap.ensure('charmcraft', classic=True)
    assert not did_something
    with pytest.raises(ValueError):
        snap.ensure('charmcraft')  # classic=False
    did_something = snap.ensure('charmcraft', classic=True)
    assert not did_something


def test_new_snap_ensure():
    snap.ensure('vlc', channel='edge')


def test_snap_ensure_revision():
    if snap.info('juju', missing_ok=True) is not None:
        snap.remove('juju')

    channels = snap._snapd._list_channels('juju')
    info = channels['3/stable']
    snap.install('juju', revision=info.revision)

    assert get_command_path('juju') == '/snap/bin/juju'

    info = snap.info('juju')
    assert info.revision == info.revision


def test_snap_start():
    snap.ensure('kube-proxy', classic=True, channel='latest/stable')
    services = snap._snapd._list_services('kube-proxy')
    assert services
    daemon = next(s for s in services if s['name'] == 'daemon')
    assert daemon.get('active')

    snap.stop('kube-proxy', 'daemon')
    services = snap._snapd._list_services('kube-proxy')
    assert services
    daemon = next(s for s in services if s['name'] == 'daemon')
    assert not daemon.get('active')

    snap.start('kube-proxy', 'daemon')
    services = snap._snapd._list_services('kube-proxy')
    assert services
    daemon = next(s for s in services if s['name'] == 'daemon')
    assert daemon['active']

    with pytest.raises(snap.SnapError):
        snap.start('kube-proxy', 'foobar')


def test_snap_stop():
    snap.ensure('kube-proxy', classic=True, channel='latest/stable')
    snap.stop('kube-proxy', 'daemon', disable=True)
    services = snap._snapd._list_services('kube-proxy')
    daemon = next(s for s in services if s['name'] == 'daemon')
    assert not daemon.get('active')
    assert not daemon.get('enabled')


def test_snap_logs():
    snap.ensure('kube-proxy', classic=True, channel='latest/stable')

    before = snap.logs('kube-proxy', num_lines=10)

    # Terrible means of populating logs
    snap.start('kube-proxy')
    snap.stop('kube-proxy')
    snap.start('kube-proxy')
    snap.stop('kube-proxy')

    after = snap.logs('kube-proxy', num_lines=10)
    assert len(before) == 10 or len(after) > len(before)


def test_snap_logs_no_services():
    snap.ensure('vlc')
    with pytest.raises(snap.SnapError) as ctx:
        snap.logs('vlc')
    assert ctx.value.kind == 'app-not-found'


def test_snap_restart():
    snap.ensure('kube-proxy', classic=True, channel='latest/stable')
    snap.restart('kube-proxy')


def test_snap_hold_refresh():
    snap.ensure('hello-world', channel='latest/stable')

    snap.hold('hello-world', duration=datetime.timedelta(days=2))
    info = snap.info('hello-world')
    assert info.hold is not None
    hold = snap._snapd._parse_timestamp(info.hold)
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


def test_snap_connect_and_disconnect():
    snap.ensure('vlc')
    # plugs = snap._snap.list_plugs('vlc')
    # assert [p for p in plugs if p.plug == 'mount-observe']

    snap.connect('vlc', 'mount-observe')
    # plugs = snap._snap.list_plugs('vlc')
    # assert [p for p in plugs if p.plug == 'mount-observe']

    snap._snapd.disconnect('vlc', 'mount-observe')
    # plugs = snap._snap.list_plugs('vlc')
    # assert not [p for p in plugs if p.plug == 'mount-observe']


def test_alias():
    snap.ensure('lxd')
    snap.alias('lxd', 'lxc', 'testlxc')

    result = check_output(['snap', 'aliases'], text=True)
    found = any(line.split() == ['lxd.lxc', 'testlxc', 'manual'] for line in result.splitlines())
    assert found, result
