"""PostgreSQL persistence package."""

# Importing models here gives Alembic one stable metadata discovery path.
from iri.db.models import (
    ConceptSearchProjection,
    DataReference,
    Fact,
    GranularPoint,
    GraphProjectionOutbox,
    IngestionJob,
)

__all__ = [
    "ConceptSearchProjection",
    "DataReference",
    "Fact",
    "GranularPoint",
    "GraphProjectionOutbox",
    "IngestionJob",
]
