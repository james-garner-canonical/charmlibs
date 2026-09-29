# 1.1.0 - 22 September 2026

First release. Provides `provider()` and `requirer()`, which return a `CharmData` describing a stand-in charm for the other end of a `certificate_transfer` relation, to deploy alongside the charm under test with `ops.testing.Juju`; and `mocked()`, which mocks the library's internals for the duration of a test -- a no-op today, since this library has nothing to mock.

This package is versioned in lockstep with `charmlibs-interfaces-certificate-transfer` and pins it exactly, because it reuses the library's private databag models. Install it as the library's `testing` extra rather than directly.
