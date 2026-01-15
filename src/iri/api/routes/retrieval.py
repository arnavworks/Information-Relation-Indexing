"""Streaming concept-first retrieval endpoint."""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from iri.api.dependencies import RetrievalServiceDependency
from iri.api.schemas import RetrievalRequest
from iri.embeddings.base import EmbeddingConfigurationError, EmbeddingProviderError

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


@router.post(
    "/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"application/x-ndjson": {}},
            "description": "Ordered route, evidence/fact, and completion events.",
        }
    },
)
async def stream_retrieval(
    request: RetrievalRequest,
    service: RetrievalServiceDependency,
) -> StreamingResponse:
    """Stream the auditable route, evidence, grounded answer, and citations."""

    try:
        prepared = await service.prepare(request)
    except EmbeddingConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="embedding provider unavailable",
        ) from exc
    return StreamingResponse(service.stream(prepared), media_type="application/x-ndjson")
