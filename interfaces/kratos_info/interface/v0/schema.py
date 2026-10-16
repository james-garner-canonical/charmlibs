"""This file defines the schemas for the provider and requirer sides of this relation interface."""

from pydantic import AnyHttpUrl, BaseModel, Field


class ProviderAppData(BaseModel):
    admin_endpoint: AnyHttpUrl = Field(
        description="Kratos admin URL.", examples=["http://10.64.140.44/testing-kratos"]
    )
    public_endpoint: AnyHttpUrl = Field(
        description="Kratos public URL.", examples=["http://10.64.140.45/testing-kratos"]
    )
    login_browser_endpoint: AnyHttpUrl = Field(
        description="The Kratos endpoint that initializes a browser-based user login flow.",
        examples=["http://10.64.140.45/testing-kratos/self-service/login/browser"],
    )
    sessions_endpoint: AnyHttpUrl = Field(
        description="The Kratos endpoint to check who the current session belongs to.",
        examples=["http://10.64.140.45/testing-kratos/sessions/whoami"],
    )
    providers_configmap_name: str = Field(
        description="The name of the ConfigMap that contains the providers configuration.",
        examples=["providers"],
    )
    schemas_configmap_name: str = Field(
        description="The name of the ConfigMap that contains the identity schemas configuration.",
        examples=["identity-schemas"],
    )
    configmaps_namespace: str = Field(
        description="The namespace where the ConfigMaps are located.", examples=["testing"]
    )
    mfa_enabled: bool = Field(description="Whether MFA is enabled.", examples=[False])
    oidc_webauthn_sequencing_enabled: bool = Field(
        description="Whether OIDC WebAuthn sequencing is enabled.", examples=[False]
    )


ProviderUnitData = None
RequirerAppData = None
RequirerUnitData = None
