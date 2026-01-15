import asyncio

from iri.api.routes.health import liveness
from iri.main import create_app


def test_liveness_does_not_require_databases() -> None:
    response = asyncio.run(liveness())

    assert response.model_dump() == {"status": "ok", "postgres": None, "neo4j": None}


def test_openapi_exposes_control_and_data_planes() -> None:
    paths = create_app().openapi()["paths"]

    assert "/v1/ingestions" in paths
    assert "/v1/retrieval/stream" in paths
