# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

from charmlibs.snap._errors import (
    APIError,
    BadResponseError,
    ChangeError,
    ChannelNotAvailableError,
    Error,
    NeedsClassicError,
    NotFoundError,
    NotInstalledError,
    OptionNotFoundError,
    RevisionNotAvailableError,
    _AlreadyInstalledError,
    _error_type_from_result_kind,
    _InterfacesUnchangedError,
    _NoUpdatesAvailableError,
)


class TestErrorTypeFromResultKind:
    def test_snap_already_installed(self):
        assert _error_type_from_result_kind('snap-already-installed') is _AlreadyInstalledError

    def test_option_not_found(self):
        assert _error_type_from_result_kind('option-not-found') is OptionNotFoundError

    def test_snap_needs_classic(self):
        assert _error_type_from_result_kind('snap-needs-classic') is NeedsClassicError

    def test_snap_not_found(self):
        assert _error_type_from_result_kind('snap-not-found') is NotFoundError

    def test_snap_not_installed(self):
        assert _error_type_from_result_kind('snap-not-installed') is NotInstalledError

    def test_snap_no_update_available(self):
        assert _error_type_from_result_kind('snap-no-update-available') is _NoUpdatesAvailableError

    def test_interfaces_unchanged(self):
        assert _error_type_from_result_kind('interfaces-unchanged') is _InterfacesUnchangedError

    def test_snap_channel_not_available(self):
        assert (
            _error_type_from_result_kind('snap-channel-not-available') is ChannelNotAvailableError
        )

    def test_snap_revision_not_available(self):
        assert (
            _error_type_from_result_kind('snap-revision-not-available')
            is RevisionNotAvailableError
        )

    def test_unknown_kind(self):
        assert _error_type_from_result_kind('bogus-kind') is APIError

    def test_empty_string(self):
        assert _error_type_from_result_kind('') is APIError

    def test_all_results_are_snap_api_error_subclasses(self):
        kinds = [
            'snap-already-installed',
            'app-not-found',
            'option-not-found',
            'snap-channel-not-available',
            'snap-needs-classic',
            'snap-not-found',
            'snap-not-installed',
            'snap-no-update-available',
            'snap-revision-not-available',
            'interfaces-unchanged',
            'bogus-kind',
            '',
        ]
        for kind in kinds:
            assert issubclass(_error_type_from_result_kind(kind), APIError), kind


class TestSnapError:
    def _make(
        self,
        message: str = 'something went wrong',
        kind: str = 'charmlibs-snap',
        value: str = 'extra-info',
        status_code: int | None = 400,
        status: str | None = 'Bad Request',
    ) -> Error:
        return Error(
            message=message,
            kind=kind,
            value=value,
            status_code=status_code,
            status=status,
        )

    def test_message(self):
        err = self._make(message='the message')
        assert err.message == 'the message'
        assert str(err) == 'the message'

    def test_kind(self):
        err = self._make(kind='snap-not-found')
        assert err.kind == 'snap-not-found'

    def test_value(self):
        err = self._make(value='myvalue')
        assert err.value == 'myvalue'

    def test_private_status(self):
        err = self._make(status_code=400, status='Bad Request')
        assert err._status_code == 400
        assert err._status == 'Bad Request'

    def test_none_status_code(self):
        err = self._make(status_code=None, status=None)
        assert err._status_code is None
        assert err._status is None

    def test_repr(self):
        err = self._make(message='msg', kind='k', value='v', status_code=400, status='Bad Request')
        r = repr(err)
        assert 'Error' in r
        assert 'msg' in r
        assert "'k'" in r
        assert "'v'" in r
        assert '400' in r
        assert 'Bad Request' in r

    def test_subclass_repr(self):
        err = NotInstalledError(
            'snap not installed',
            kind='snap-not-installed',
            value='',
            status_code=404,
            status='Not Found',
        )
        assert 'NotInstalledError' in repr(err)

    def test_snap_api_error_is_subclass_of_snap_error(self):
        assert issubclass(APIError, Error)

    def test_snap_bad_response_error_is_subclass(self):
        assert issubclass(BadResponseError, Error)
        assert not issubclass(BadResponseError, APIError)

    def test_snap_change_error_is_subclass(self):
        assert issubclass(ChangeError, APIError)
        assert issubclass(ChangeError, Error)

    def test_specific_errors_are_snap_api_error_subclasses(self):
        for cls in [
            _AlreadyInstalledError,
            NotFoundError,
            NotInstalledError,
            NeedsClassicError,
            OptionNotFoundError,
            _NoUpdatesAvailableError,
            _InterfacesUnchangedError,
        ]:
            assert issubclass(cls, APIError), cls
            assert issubclass(cls, Error), cls
