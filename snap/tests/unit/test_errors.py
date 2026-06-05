# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

import builtins
import inspect

import pytest

from charmlibs.snap import _errors

# Error types in the module that are intentionally outside the snapd API error hierarchy.
_NON_API_ERROR_TYPES = frozenset({
    _errors.Error,
    _errors.BadResponseError,
    _errors.ConnectionError,
    _errors.TimeoutError,
})


@pytest.fixture(scope='module')
def error_types() -> frozenset[type[BaseException]]:
    """Every class defined in the _errors module, including private types."""
    return frozenset(
        obj
        for _, obj in inspect.getmembers(_errors, inspect.isclass)
        if obj.__module__ == _errors.__name__
    )


class TestErrorHierarchy:
    def test_all_error_types_subclass_error(self, error_types: frozenset[type[BaseException]]):
        for cls in error_types:
            assert issubclass(cls, _errors.Error)

    def test_api_error_subclasses(self, error_types: frozenset[type[BaseException]]):
        for cls in error_types - _NON_API_ERROR_TYPES:
            assert issubclass(cls, _errors.APIError)

    def test_non_api_error_subclasses(self):
        for cls in _NON_API_ERROR_TYPES:
            assert not issubclass(cls, _errors.APIError)

    def test_timeout_and_connection_errors_subclass_builtins(self):
        assert issubclass(_errors.TimeoutError, builtins.TimeoutError)
        assert issubclass(_errors.ConnectionError, builtins.ConnectionError)


class TestErrorTypeFromResultKind:
    @pytest.mark.parametrize(
        ('kind', 'expected'),
        [
            ('snap-already-installed', _errors._AlreadyInstalledError),
            ('app-not-found', _errors.AppNotFoundError),
            ('option-not-found', _errors.OptionNotFoundError),
            ('snap-channel-not-available', _errors.ChannelNotAvailableError),
            ('snap-needs-classic', _errors.NeedsClassicError),
            ('snap-not-found', _errors.NotFoundError),
            ('snap-not-installed', _errors.NotInstalledError),
            ('snap-no-update-available', _errors._NoUpdatesAvailableError),
            ('snap-revision-not-available', _errors.RevisionNotAvailableError),
            ('interfaces-unchanged', _errors._InterfacesUnchangedError),
            ('bogus-kind', _errors.APIError),
            ('', _errors.APIError),
        ],
    )
    def test_error_type_from_result_kind(self, kind: str, expected: type[_errors.APIError]):
        assert _errors._error_type_from_result_kind(kind) is expected


class TestSnapError:
    def test_attributes(self):
        err = _errors.Error(
            'the message',
            kind='the-kind',
            value='the-value',
            status_code=400,
            status='Bad Request',
        )
        assert err.message == 'the message'
        assert str(err) == 'the message'
        assert err.kind == 'the-kind'
        assert err.value == 'the-value'
        assert err._status_code == 400
        assert err._status == 'Bad Request'

    def test_repr(self):
        err = _errors.Error(
            'my very unique error message',
            kind='unique-kind',
            value='unique-value',
            status_code=400,
            status='unique status string',
        )
        r = repr(err)
        assert str(type(err).__name__) in r
        assert 'my very unique error message' in r
        assert "'unique-kind'" in r
        assert "'unique-value'" in r
        assert '400' in r
        assert 'unique status string' in r
