"""This file defines the schemas for the provider and requirer sides of the azure_service_principal interface."""

from pydantic import BaseModel, ConfigDict, Field


class _BareStringDatabag(BaseModel):
    """Base class for databag models that don't strictly JSON encode all entries."""

    @staticmethod
    def __juju_decoder__(value: str) -> str:
        """Pass Juju's string through unmodified to be decoded by individual field validators."""
        return value

    @staticmethod
    def __juju_encoder__(value: str | None) -> str:
        """Convert `None` to "", erasing the value; Ops will error on a non-string."""
        return "" if value is None else value


class ProviderAppData(_BareStringDatabag):
    """Credentials for an Azure Service Principal."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    subscription_id: str | None = Field(
        default=None,
        alias="subscription-id",
        description="The unique identifier for an Azure subscription.",
        examples=["12345678-1234-1234-1234-1234567890ab"],
        title="Subscription ID",
    )

    tenant_id: str | None = Field(
        default=None,
        alias="tenant-id",
        description="The unique identifier of the Azure Active Directory (Entra ID) tenant.",
        examples=["87654321-4321-4321-4321-ba0987654321"],
        title="Tenant ID",
    )

    secret_extra: str | None = Field(
        default=None,
        alias="secret-extra",
        description=(
            "A Juju Secret ID that points to a secret containing client-id (the Application ID"
            " for the service principal) and client-secret (used for authentication)."
        ),
        examples=["secret://91f805c5-5b49-47a3-8e7b-70befa766caf/d40rbhnmp25c76d6bdn0"],
        title="Credentials Secret ID",
    )


RequirerAppData = None
ProviderUnitData = None
RequirerUnitData = None
