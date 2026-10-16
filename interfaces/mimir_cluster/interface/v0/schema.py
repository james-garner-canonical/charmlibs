"""This file defines the schemas for the provider and requirer sides of this relation interface."""

import enum
import typing

import pydantic


class MimirRole(str, enum.Enum):
    """Mimir component role names."""

    overrides_exporter = "overrides-exporter"
    query_scheduler = "query-scheduler"
    flusher = "flusher"
    query_frontend = "query-frontend"
    querier = "querier"
    store_gateway = "store-gateway"
    ingester = "ingester"
    distributor = "distributor"
    ruler = "ruler"
    alertmanager = "alertmanager"
    compactor = "compactor"

    # meta-roles
    read = "read"
    write = "write"
    backend = "backend"
    all = "all"


class Scheme(str, enum.Enum):
    """Scheme strings."""

    http = "http"
    https = "https"


class ProviderAppData(pydantic.BaseModel):
    mimir_config: dict[str, typing.Any] = pydantic.Field(
        description="Mimir configuration for the workers to use.",
        examples=[
            {
                'target': 'all',
                'server': {'http_listen_port': 8080},
                'blocks_storage': {
                    'backend': 'filesystem',
                    'filesystem': {'dir': '/data/blocks'},
                },
            }
        ],
    )


class JujuTopology(pydantic.BaseModel):
    unit: str
    app: str
    charm: str
    model: str
    # in pydantic v2, `model_` is a protected namespace
    juju_model_uuid: str = pydantic.Field(description="Juju model UUID.", alias="model_uuid")


class RequirerUnitData(pydantic.BaseModel):
    juju_topology: JujuTopology = pydantic.Field(
        description="Juju topology of the worker unit.",
        examples=[
            {
                'unit': 'worker/0',
                'app': 'worker',
                'charm': 'mimir-worker-k8s',
                'model': 'cos',
                'model_uuid': '58b48ff0-608b-435f-83b9-ea643e0b98db',
            }
        ],
    )
    address: str = pydantic.Field(
        description="Address of the worker unit.",
        examples=['worker-0.worker-endpoints.cos.svc.cluster.local'],
    )
    port: int = pydantic.Field(description="Port of the worker unit.", examples=[8080])
    scheme: Scheme = pydantic.Field(
        description="Scheme used to reach the worker unit.", examples=['http']
    )


class RequirerAppData(pydantic.BaseModel):
    roles: list[MimirRole] = pydantic.Field(
        description="Roles the worker application runs with.", examples=[['read']]
    )


ProviderUnitData = None
