# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.


from charmlibs.interfaces import tls_certificates, tls_certificates_testing


def test_versions_match():
    assert tls_certificates_testing.__version__ == tls_certificates.__version__
