import asyncio
from typing import Any

import pytest
from pydantic import SecretStr

from iri.api.schemas import RetrievalRequest
from iri.constants import EMBEDDING_DIMENSIONS
from iri.embeddings.base import EmbeddingConfigurationError
from iri.embeddings.gemini import GeminiEmbeddingProvider
from iri.services.retrieval import RetrievalService


class StubEmbeddingProvider:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def embed_query(self, query: str) -> list[float]:
        self.queries.append(query)
        return [0.25] * EMBEDDING_DIMENSIONS

    async def embed_document(self, title: str, text: str) -> list[float]:
        return [0.5] * EMBEDDING_DIMENSIONS


def test_retrieval_prepares_missing_embedding_with_provider() -> None:
    provider = StubEmbeddingProvider()
    service = RetrievalService(Any, Any, provider)  # type: ignore[arg-type]
    request = RetrievalRequest(query="Who owns employee-created IP?")

    prepared = asyncio.run(service.prepare(request))

    assert provider.queries == [request.query]
    assert prepared.query_embedding == [0.25] * EMBEDDING_DIMENSIONS
    assert request.query_embedding is None


def test_retrieval_preserves_supplied_embedding() -> None:
    provider = StubEmbeddingProvider()
    service = RetrievalService(Any, Any, provider)  # type: ignore[arg-type]
    vector = [0.75] * EMBEDDING_DIMENSIONS

    prepared = asyncio.run(
        service.prepare(RetrievalRequest(query="Replay", query_embedding=vector))
    )

    assert prepared.query_embedding == vector
    assert provider.queries == []


def test_gemini_provider_requires_key_only_when_called() -> None:
    provider = GeminiEmbeddingProvider(api_key=None, model="gemini-embedding-2")

    with pytest.raises(EmbeddingConfigurationError, match="GEMINI_API_KEY"):
        asyncio.run(provider.embed_query("test"))


def test_gemini_provider_accepts_secret_key_without_eager_network_call() -> None:
    provider = GeminiEmbeddingProvider(
        api_key=SecretStr("not-a-real-key"),
        model="gemini-embedding-2",
    )

    assert provider._client is None
