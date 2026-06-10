# Copyright 2025 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Manage TLS certificates using the ``tls-certificates`` interface (V1).

This is a port of ``tls_certificates_interface.tls_certificates`` v4.22.

The library implements the requirer side of the interface via
:class:`TLSCertificatesRequiresV4` and the provider side via
:class:`TLSCertificatesProvidesV4`. The requirer's private key is generated
locally by the library and stored in a Juju secret; only certificate signing
requests and the resulting certificates cross the relation.

For the wire-level specification of the interface itself, see the
``tls-certificates`` v1 interface reference. For a tutorial, how-to guides,
and design discussion of this library, see the docs alongside the source in
the ``charmlibs`` repository.
"""

from ._tls_certificates import (
    Certificate,
    CertificateAvailableEvent,
    CertificateDeniedEvent,
    CertificateError,
    CertificateRequestAttributes,
    CertificateRequestErrorCode,
    CertificateSigningRequest,
    CertificatesRequirerCharmEvents,
    DataValidationError,
    Mode,
    PrivateKey,
    ProviderCertificate,
    ProviderCertificateError,
    RequirerCertificateRequest,
    TLSCertificatesError,
    TLSCertificatesProvidesV4,
    TLSCertificatesRequiresV4,
    calculate_relative_datetime,
    chain_has_valid_order,
    generate_ca,
    generate_certificate,
    generate_csr,
    generate_private_key,
)
from ._version import __version__ as __version__

__all__ = [
    "Certificate",
    "CertificateAvailableEvent",
    "CertificateDeniedEvent",
    "CertificateError",
    "CertificateRequestAttributes",
    "CertificateRequestErrorCode",
    "CertificateSigningRequest",
    "CertificatesRequirerCharmEvents",
    "DataValidationError",
    "Mode",
    "PrivateKey",
    "ProviderCertificate",
    "ProviderCertificateError",
    "RequirerCertificateRequest",
    # only the names listed in __all__ are imported when executing:
    # from charmlibs.tls_certificates import *
    "TLSCertificatesError",
    "TLSCertificatesProvidesV4",
    "TLSCertificatesRequiresV4",
    "calculate_relative_datetime",
    "chain_has_valid_order",
    "generate_ca",
    "generate_certificate",
    "generate_csr",
    "generate_private_key",
]
