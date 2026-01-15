"""Google Gemini embedding adapter with retrieval-specific input formatting."""

import math
from typing import Any

from google import genai
from google.genai import types
from pydantic import SecretStr

from iri.constants import EMBEDDING_DIMENSIONS
from iri.embeddings.base import (
    EmbeddingConfigurationError,
    EmbeddingProviderError,
)


class GeminiEmbeddingProvider:
    """Generate compatible query and concept-summary vectors through Gemini.

    ``gemini-embedding-001`` does not accept the legacy ``task_type`` parameter.
    Instead, Google specifies asymmetric text prefixes for retrieval queries and
    documents. Both paths request the database's fixed 1,536 dimensions.
    """

    def __init__(self, api_key: SecretStr | None, model: str) -> None:
        self._api_key = api_key
        self._model = model
        self._client: Any | None = None

    async def embed_query(self, query: str) -> list[float]:
        prepared = f"task: search result | query: {query}"
        return await self._embed(prepared)

    async def embed_document(self, title: str, text: str) -> list[float]:
        prepared = f"title: {title or 'none'} | text: {text}"
        return await self._embed(prepared)

    async def _embed(self, content: str) -> list[float]:
        client = self._get_client()
        try:
            response = await client.aio.models.embed_content(
                model=self._model,
                contents=content,
                config=types.EmbedContentConfig(
                    output_dimensionality=EMBEDDING_DIMENSIONS,
                ),
            )
        except EmbeddingConfigurationError:
            raise
        except Exception as exc:
            raise EmbeddingProviderError("Gemini embedding request failed") from exc

        embeddings = response.embeddings or []
        if len(embeddings) != 1 or embeddings[0].values is None:
            raise EmbeddingProviderError("Gemini returned no usable embedding")
        values = [float(value) for value in embeddings[0].values]
        if len(values) != EMBEDDING_DIMENSIONS:
            raise EmbeddingProviderError(
                f"Gemini returned {len(values)} dimensions; expected {EMBEDDING_DIMENSIONS}"
            )
        if not all(math.isfinite(value) for value in values):
            raise EmbeddingProviderError("Gemini returned a non-finite embedding value")
        return values

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._api_key is None or not self._api_key.get_secret_value():
            raise EmbeddingConfigurationError(
                "GEMINI_API_KEY is required when query_embedding is omitted"
            )
        self._client = genai.Client(api_key=self._api_key.get_secret_value())
        return self._client

    async def aclose(self) -> None:
        if self._client is None:
            return
        await self._client.aio.aclose()
        self._client.close()
        self._client = None
