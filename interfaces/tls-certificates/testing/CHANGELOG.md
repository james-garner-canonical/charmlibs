# 1.11.0 - 21 September 2026

First release. Provides `provider()` and `requirer()`, which return a `CharmData` describing a stand-in charm for the other end of a `tls-certificates` relation, to deploy alongside the charm under test with `ops.testing.Juju`; `Outcome`, which chooses what the stand-in provider does with each request; and `mocked()`, which replaces the library's private key generation with a pre-generated key for the duration of a test.

This package is versioned in lockstep with `charmlibs-interfaces-tls-certificates` and pins it exactly, because it reuses the library's private wire format. Install it as the library's `testing` extra rather than directly.
