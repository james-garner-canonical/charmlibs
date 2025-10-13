"""This file defines the schemas for the provider and requirer sides of the `tls-certificates` interface.

It exposes two interfaces.schema_base.DataBagSchema subclasses called:
- ProviderSchema
- RequirerSchema

Examples:
    ProviderSchema:
        unit: <empty>
        app: {
            "certificates": [
                {
                    "ca": "-----BEGIN CERTIFICATE----- ...",
                    "chain": [
                        "-----BEGIN CERTIFICATE----- ...",
                        "-----BEGIN CERTIFICATE----- ..."
                    ],
                    "certificate_signing_request": "-----BEGIN CERTIFICATE REQUEST----- ...",
                    "certificate": "-----BEGIN CERTIFICATE----- ..."
                }
            ]
        }
    RequirerSchema:
        unit: {
            "certificate_signing_requests": [
                {
                    "certificate_signing_request": "-----BEGIN CERTIFICATE REQUEST----- ...",
                    "ca": true
                }
            ]
        }
        app:  <empty>
"""

from interface_tester.schema_base import DataBagSchema  # pyright: ignore[reportMissingTypeStubs]
from pydantic import BaseModel, Field, Json


class Certificate(BaseModel):
    """Certificate model."""

    ca: str = Field(description="The signing certificate authority.")
    certificate_signing_request: str = Field(description="Certificate signing request.")
    certificate: str = Field(description="Certificate.")
    chain: list[str] | None = Field(description="List of certificates in the chain.")
    recommended_expiry_notification_time: int | None = Field(
        description="Recommended expiry notification time in seconds."
    )
    revoked: bool | None = Field(description="Whether the certificate is revoked.")


class CertificateSigningRequest(BaseModel):
    """Certificate signing request model."""

    certificate_signing_request: str = Field(description="Certificate signing request.")
    ca: bool | None = Field(description="Whether the certificate is a CA.")


class ProviderApplicationData(BaseModel):
    """Provider application data model."""

    certificates: Json[list[Certificate]] = Field(description="List of certificates.")


class RequirerData(BaseModel):
    """Requirer data model.

    The same model is used for the unit and application data.
    """

    certificate_signing_requests: Json[list[CertificateSigningRequest]] = Field(
        description="List of certificate signing requests."
    )


class ProviderSchema(DataBagSchema):
    """Provider schema for TLS Certificates."""

    app: ProviderApplicationData  # pyright: ignore[reportGeneralTypeIssues,reportIncompatibleVariableOverride]


class RequirerSchema(DataBagSchema):
    """Requirer schema for TLS Certificates."""

    app: RequirerData  # pyright: ignore[reportGeneralTypeIssues,reportIncompatibleVariableOverride]
    unit: RequirerData  # pyright: ignore[reportGeneralTypeIssues,reportIncompatibleVariableOverride]
