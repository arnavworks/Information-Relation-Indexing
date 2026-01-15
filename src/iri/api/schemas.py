"""External API contracts; persistence models are never exposed directly."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from iri.constants import EMBEDDING_DIMENSIONS
from iri.db.models import DataSourceType, FactValueType, IngestionStatus


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IngestionCreate(StrictRequest):
    source_type: DataSourceType
    source_uri: str = Field(min_length=1, max_length=8_192)
    source_name: str = Field(min_length=1, max_length=512)
    media_type: str | None = Field(default=None, max_length=255)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int | None = Field(default=None, ge=0)
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionAccepted(BaseModel):
    job_id: UUID
    dri_id: int
    dri_code: str
    status: IngestionStatus
    reused: bool = False


class IngestionStatusResponse(BaseModel):
    job_id: UUID
    dri_id: int
    dri_code: str
    status: IngestionStatus
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class RetrievalMode(StrEnum):
    EVIDENCE = "evidence"
    FACTS = "facts"


class RetrievalRequest(StrictRequest):
    query: str = Field(min_length=1, max_length=10_000)
    # Normally generated server-side by Gemini. Supplying a vector remains useful
    # for deterministic replay and deployments with an external embedding gateway.
    query_embedding: list[float] | None = Field(
        default=None,
        min_length=EMBEDDING_DIMENSIONS,
        max_length=EMBEDDING_DIMENSIONS,
    )
    mode: RetrievalMode = RetrievalMode.EVIDENCE
    concept_limit: int = Field(default=8, ge=1, le=100)


class FactCreate(StrictRequest):
    """Validation contract mirrored by PostgreSQL CHECK constraints."""

    info_uid: UUID
    source_point_id: UUID
    name: str = Field(min_length=1, max_length=500)
    value_type: FactValueType
    numeric_value: Decimal | None = None
    date_value: date | None = None
    text_value: str | None = None
    calculation_expression: str | None = None

    @model_validator(mode="after")
    def validate_typed_value(self) -> "FactCreate":
        values = [self.numeric_value, self.date_value, self.text_value]
        if sum(value is not None for value in values) != 1:
            raise ValueError("exactly one typed fact value is required")
        if self.value_type in {FactValueType.NUMBER, FactValueType.CALCULATION}:
            if self.numeric_value is None:
                raise ValueError("numeric facts require numeric_value")
        elif self.value_type is FactValueType.DATE and self.date_value is None:
            raise ValueError("date facts require date_value")
        elif self.value_type is FactValueType.TEXT and self.text_value is None:
            raise ValueError("text facts require text_value")
        if self.value_type is FactValueType.CALCULATION and not self.calculation_expression:
            raise ValueError("calculated facts require calculation_expression")
        return self


class HealthResponse(BaseModel):
    status: str
    postgres: bool | None = None
    neo4j: bool | None = None


class GraphDataReference(BaseModel):
    dri_id: int
    dri_code: str
    source_name: str
    source_type: DataSourceType


class GraphPoint(BaseModel):
    point_id: UUID
    dri_id: int
    coordinate: str
    raw_text: str


class GraphFact(BaseModel):
    fact_id: UUID
    info_uid: UUID
    source_point_id: UUID
    name: str
    value_type: FactValueType
    value: str
    unit: str | None
    currency: str | None


class GraphAppearance(BaseModel):
    sinfo_uid: str
    dri_id: int
    point_ids: list[UUID]
    coordinates: list[str]
    summary_line_1: str
    summary_line_2: str


class GraphConcept(BaseModel):
    info_uid: UUID
    name: str
    summary_line_1: str
    summary_line_2: str
    appearances: list[GraphAppearance]


class GraphSnapshotResponse(BaseModel):
    data_references: list[GraphDataReference]
    concepts: list[GraphConcept]
    points: list[GraphPoint]
    facts: list[GraphFact]
