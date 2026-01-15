"""Provider-neutral embedding contract used by retrieval and ingestion."""

from typing import Protocol


class EmbeddingProvider(Protocol):
    async def embed_query(self, query: str) -> list[float]:
        """Embed a search query in the concept-retrieval vector space."""

    async def embed_document(self, title: str, text: str) -> list[float]:
        """Embed a two-line Info_UID summary for indexing."""


class EmbeddingConfigurationError(RuntimeError):
    """The selected embedding provider lacks required configuration."""


class EmbeddingProviderError(RuntimeError):
    """The provider failed or returned an invalid embedding."""
