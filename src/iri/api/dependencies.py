"""FastAPI dependency assembly for request-scoped services."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from iri.core.config import get_settings
from iri.db.session import get_session
from iri.embeddings.gemini import GeminiEmbeddingProvider
from iri.generation.gemini import GeminiAnswerGenerator
from iri.graph.gateway import Neo4jConceptGateway
from iri.repositories.postgres import IngestionRepository, RetrievalRepository
from iri.services.ingestion import IngestionService
from iri.services.retrieval import RetrievalService

SessionDependency = Annotated[AsyncSession, Depends(get_session)]


@lru_cache(maxsize=1)
def get_embedding_provider() -> GeminiEmbeddingProvider:
    settings = get_settings()
    return GeminiEmbeddingProvider(settings.gemini_api_key, settings.embedding_model)


def get_ingestion_service(session: SessionDependency) -> IngestionService:
    return IngestionService(IngestionRepository(session))


def get_retrieval_service(session: SessionDependency) -> RetrievalService:
    settings = get_settings()
    return RetrievalService(
        RetrievalRepository(session),
        Neo4jConceptGateway(),
        get_embedding_provider(),
        GeminiAnswerGenerator(settings.gemini_api_key, settings.answer_model),
        settings.answer_max_sources,
    )


IngestionServiceDependency = Annotated[IngestionService, Depends(get_ingestion_service)]
RetrievalServiceDependency = Annotated[RetrievalService, Depends(get_retrieval_service)]
