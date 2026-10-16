from pydantic import BaseModel, Field


class GrafanaDatasource(BaseModel):
    type: str = Field(
        description="Type of the datasource, typically one of "
        "https://grafana.com/docs/grafana/latest/datasources/#built-in-core-data-sources.",
        examples=["tempo", "loki", "prometheus", "elasticsearch"],
    )
    uid: str = Field(description="Grafana datasource UID, as assigned by Grafana.")
    grafana_uid: str = Field(description="Grafana UID.")


class GrafanaSourceAppData(BaseModel):
    """Application databag model for the requirer side of this interface."""

    datasources: list[GrafanaDatasource] = Field(
        description="Fully specified datasources exposed by this application, sorted by UID.",
        examples=[
            [
                {
                    'type': 'tempo',
                    'uid': '0000-0000-0000-0001',
                    'grafana_uid': '0000-0000-0000-0002',
                },
                {
                    'type': 'prometheus',
                    'uid': '0000-0000-0000-0003',
                    'grafana_uid': '0000-0000-0000-0004',
                },
            ]
        ],
    )


ProviderAppData = GrafanaSourceAppData
ProviderUnitData = None
RequirerAppData = GrafanaSourceAppData
RequirerUnitData = None
