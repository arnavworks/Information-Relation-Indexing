"""Versioned hand-off contract for parallel extraction agents.

Agents emit this structure; a single validator/persistence worker resolves local
point keys to PostgreSQL UUIDs and writes graph outbox events. Agents never write
Neo4j directly, which removes cross-store races and partial concept topologies.
"""

from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from iri.db.models import FactValueType


class ExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PointDraft(ExtractionModel):
    local_key: str = Field(min_length=1, max_length=200)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    point_number: int = Field(ge=1)
    raw_text: str = Field(min_length=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def ordered_ranges(self) -> "PointDraft":
        if self.page_end < self.page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        if self.char_end is not None and (
            self.char_start is None or self.char_end <= self.char_start
        ):
            raise ValueError("char_end requires a smaller char_start")
        return self


class ConceptDraft(ExtractionModel):
    info_uid: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=500)
    summary_line_1: str = Field(min_length=1, max_length=1000)
    summary_line_2: str = Field(min_length=1, max_length=1000)


class AppearanceDraft(ExtractionModel):
    sinfo_uid: UUID = Field(default_factory=uuid4)
    info_uid: UUID
    point_local_keys: tuple[str, ...] = Field(min_length=1)
    source_summary_line_1: str = Field(min_length=1, max_length=1000)
    source_summary_line_2: str = Field(min_length=1, max_length=1000)


class FactDraft(ExtractionModel):
    info_uid: UUID
    source_point_local_key: str
    name: str = Field(min_length=1, max_length=500)
    value_type: FactValueType
    numeric_value: Decimal | None = None
    date_value: date | None = None
    text_value: str | None = None
    unit: str | None = Field(default=None, max_length=100)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    as_of_date: date | None = None
    calculation_expression: str | None = None
    input_fact_names: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_typed_value(self) -> "FactDraft":
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


class ExtractionBundle(ExtractionModel):
    schema_version: Literal["1.0"] = "1.0"
    dri_id: int = Field(ge=1)
    extraction_version: str = Field(min_length=1, max_length=64)
    agent_id: str = Field(min_length=1, max_length=255)
    points: tuple[PointDraft, ...]
    concepts: tuple[ConceptDraft, ...]
    appearances: tuple[AppearanceDraft, ...]
    facts: tuple[FactDraft, ...] = ()
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> "ExtractionBundle":
        point_keys = [point.local_key for point in self.points]
        if len(point_keys) != len(set(point_keys)):
            raise ValueError("point local_key values must be unique")
        concept_ids = {concept.info_uid for concept in self.concepts}
        known_points = set(point_keys)
        for appearance in self.appearances:
            if appearance.info_uid not in concept_ids:
                raise ValueError(f"appearance references unknown Info_UID {appearance.info_uid}")
            if not set(appearance.point_local_keys) <= known_points:
                raise ValueError("appearance references an unknown point local_key")
        for fact in self.facts:
            if fact.info_uid not in concept_ids:
                raise ValueError(f"fact references unknown Info_UID {fact.info_uid}")
            if fact.source_point_local_key not in known_points:
                raise ValueError("fact references an unknown point local_key")
        return self
