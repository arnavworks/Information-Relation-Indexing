"""Liveness and dependency-aware readiness checks."""

import anyio
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from iri.api.dependencies import SessionDependency
from iri.api.schemas import HealthResponse
from iri.graph.gateway import Neo4jConceptGateway

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse)
async def readiness(session: SessionDependency, response: Response) -> HealthResponse:
    postgres_ok = False
    neo4j_ok = False
    try:
        postgres_ok = bool((await session.execute(text("SELECT 1"))).scalar_one() == 1)
    except Exception:
        postgres_ok = False
    try:
        neo4j_ok = await anyio.to_thread.run_sync(Neo4jConceptGateway().ping)
    except Exception:
        neo4j_ok = False

    ready = postgres_ok and neo4j_ok
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if ready else "unavailable",
        postgres=postgres_ok,
        neo4j=neo4j_ok,
    )
