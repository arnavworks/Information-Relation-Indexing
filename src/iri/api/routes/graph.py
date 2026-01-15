"""Read-only relational graph projection for the visual interface."""

from fastapi import APIRouter

from iri.api.dependencies import SessionDependency
from iri.api.schemas import GraphSnapshotResponse
from iri.graph.gateway import Neo4jConceptGateway
from iri.services.graph_snapshot import GraphSnapshotService

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/snapshot", response_model=GraphSnapshotResponse)
async def graph_snapshot(session: SessionDependency) -> GraphSnapshotResponse:
    return await GraphSnapshotService(session, Neo4jConceptGateway()).get()
