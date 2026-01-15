"""SQLModel definitions for the physical, coordinate, numeric, and search layers.

PostgreSQL owns source identity and verbatim evidence. Neo4j may point into these
tables, but it never duplicates raw point text or numerical fact values.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import VECTOR  # type: ignore[import-untyped]
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel

from iri.constants import EMBEDDING_DIMENSIONS


def utc_now() -> datetime:
    """Return a timezone-aware timestamp for non-database construction paths."""

    return datetime.now(UTC)


class DataSourceType(StrEnum):
    PDF = "pdf"
    DOCUMENT = "document"
    SPREADSHEET = "spreadsheet"
    JSON = "json"
    DATABASE = "database"
    STREAM = "stream"
    OTHER = "other"


class IngestionStatus(StrEnum):
    REGISTERED = "registered"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


class FactValueType(StrEnum):
    NUMBER = "number"
    DATE = "date"
    TEXT = "text"
    CALCULATION = "calculation"


class GraphEventType(StrEnum):
    CONCEPT_UPSERT = "concept_upsert"
    APPEARANCE_UPSERT = "appearance_upsert"
    HIERARCHY_UPSERT = "hierarchy_upsert"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"


def enum_values(enum_type: type[StrEnum]) -> list[str]:
    """Persist stable enum values rather than Python member names."""

    return [member.value for member in enum_type]


class DataReference(SQLModel, table=True):
    """The immutable DRI master-ledger entry for one physical source.

    ``id=42`` is rendered as ``DRI42``. Database permissions should permit the
    ingestion role to INSERT and SELECT this table, but never UPDATE or DELETE it.
    """

    __tablename__ = "data_references"
    __table_args__ = (
        UniqueConstraint("content_sha256", "source_uri", name="uq_dri_content_source"),
        CheckConstraint("char_length(content_sha256) = 64", name="ck_dri_sha256_length"),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    immutable_uid: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), unique=True, nullable=False),
    )
    source_type: DataSourceType = Field(
        sa_column=Column(
            SAEnum(
                DataSourceType,
                name="data_source_type",
                native_enum=False,
                length=32,
                values_callable=enum_values,
            )
        )
    )
    source_uri: str = Field(sa_column=Column(Text, nullable=False))
    source_name: str = Field(sa_column=Column(String(512), nullable=False))
    media_type: str | None = Field(default=None, sa_column=Column(String(255)))
    content_sha256: str = Field(sa_column=Column(String(64), nullable=False, index=True))
    byte_size: int | None = Field(default=None, ge=0, sa_column=Column(BigInteger))
    source_metadata: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    registered_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    @property
    def reference_code(self) -> str:
        """Return the human-auditable ``DRI(N)`` identifier."""

        if self.id is None:
            raise ValueError("A DRI code is unavailable until the row has been flushed")
        return f"DRI{self.id}"


class GranularPoint(SQLModel, table=True):
    """A verbatim evidence leaf with a deterministic DRI/page/point coordinate."""

    __tablename__ = "granular_points"
    __table_args__ = (
        UniqueConstraint(
            "dri_id", "page_start", "page_end", "point_number", name="uq_point_coordinate"
        ),
        CheckConstraint("page_start > 0", name="ck_point_page_start_positive"),
        CheckConstraint("page_end >= page_start", name="ck_point_page_order"),
        CheckConstraint("point_number > 0", name="ck_point_number_positive"),
        CheckConstraint("char_start IS NULL OR char_start >= 0", name="ck_point_char_start"),
        CheckConstraint(
            "char_end IS NULL OR (char_start IS NOT NULL AND char_end > char_start)",
            name="ck_point_char_order",
        ),
    )

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )
    dri_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("data_references.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )
    )
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    point_number: int = Field(ge=1)
    raw_text: str = Field(sa_column=Column(Text, nullable=False))
    text_sha256: str = Field(sa_column=Column(String(64), nullable=False))
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=1)
    extraction_version: str = Field(default="1", sa_column=Column(String(64), nullable=False))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    @property
    def coordinate(self) -> str:
        """Render the canonical ``DRI(N).page-page.point`` citation."""

        return f"DRI{self.dri_id}.{self.page_start}-{self.page_end}.{self.point_number}"


class ConceptSearchProjection(SQLModel, table=True):
    """Vector-search projection of a canonical Neo4j ``Info_UID`` node.

    It contains only the approved two-line concept synopsis and its embedding.
    Raw evidence is deliberately absent, preventing semantic search from becoming
    an uncited answer store.
    """

    __tablename__ = "concept_search_projections"
    __table_args__ = (
        Index(
            "ix_concept_embedding_hnsw_cosine",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    info_uid: UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    summary_line_1: str = Field(sa_column=Column(String(1000), nullable=False))
    summary_line_2: str = Field(sa_column=Column(String(1000), nullable=False))
    embedding: Any = Field(sa_column=Column(VECTOR(EMBEDDING_DIMENSIONS), nullable=False))
    embedding_model: str = Field(sa_column=Column(String(255), nullable=False))
    summary_version: int = Field(default=1, ge=1)
    # The graph projector flips this only after all Neo4j pointers exist. This
    # prevents an eventually-consistent concept from entering online retrieval.
    is_routable: bool = Field(default=False, index=True)
    indexed_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    @property
    def summary(self) -> str:
        return f"{self.summary_line_1}\n{self.summary_line_2}"


class Fact(SQLModel, table=True):
    """A typed numerical/date fact linked to a concept and exact source point.

    The CHECK constraints ensure each row has exactly the value representation
    declared by ``value_type``. Derived calculations additionally preserve their
    expression and input fact IDs for replay and audit.
    """

    __tablename__ = "facts"
    __table_args__ = (
        CheckConstraint(
            "(value_type IN ('number', 'calculation') AND numeric_value IS NOT NULL "
            "AND date_value IS NULL AND text_value IS NULL) OR "
            "(value_type = 'date' AND date_value IS NOT NULL "
            "AND numeric_value IS NULL AND text_value IS NULL) OR "
            "(value_type = 'text' AND text_value IS NOT NULL "
            "AND numeric_value IS NULL AND date_value IS NULL)",
            name="ck_fact_typed_value",
        ),
        CheckConstraint(
            "value_type != 'calculation' OR calculation_expression IS NOT NULL",
            name="ck_fact_calculation_expression",
        ),
        UniqueConstraint("info_uid", "name", "source_point_id", name="uq_fact_origin"),
    )

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )
    info_uid: UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False, index=True))
    source_point_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("granular_points.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )
    )
    name: str = Field(sa_column=Column(String(500), nullable=False))
    value_type: FactValueType = Field(
        sa_column=Column(
            SAEnum(
                FactValueType,
                name="fact_value_type",
                native_enum=False,
                length=32,
                values_callable=enum_values,
            )
        )
    )
    numeric_value: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(38, 12)),
    )
    date_value: date | None = None
    text_value: str | None = Field(default=None, sa_column=Column(Text))
    unit: str | None = Field(default=None, sa_column=Column(String(100)))
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    as_of_date: date | None = None
    calculation_expression: str | None = Field(default=None, sa_column=Column(Text))
    input_fact_ids: list[UUID] = Field(
        default_factory=list,
        sa_column=Column(
            ARRAY(PG_UUID(as_uuid=True)),
            nullable=False,
            server_default=text("'{}'::uuid[]"),
        ),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class IngestionJob(SQLModel, table=True):
    """Durable state for asynchronous extraction and graph projection work."""

    __tablename__ = "ingestion_jobs"

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )
    dri_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("data_references.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )
    )
    status: IngestionStatus = Field(
        default=IngestionStatus.QUEUED,
        sa_column=Column(
            SAEnum(
                IngestionStatus,
                name="ingestion_status",
                native_enum=False,
                length=32,
                values_callable=enum_values,
            ),
            nullable=False,
        ),
    )
    idempotency_key: str = Field(sa_column=Column(String(255), nullable=False, unique=True))
    request_fingerprint: str = Field(sa_column=Column(String(64), nullable=False))
    error_code: str | None = Field(default=None, sa_column=Column(String(100)))
    error_detail: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class GraphProjectionOutbox(SQLModel, table=True):
    """Transactional outbox preventing unsafe PostgreSQL/Neo4j dual writes.

    Extraction commits evidence, facts, search projections, and these events in
    one PostgreSQL transaction. A graph projector retries pending events and marks
    them published only after Neo4j acknowledges the idempotent update.
    """

    __tablename__ = "graph_projection_outbox"
    __table_args__ = (
        Index("ix_graph_outbox_pending", "status", "created_at"),
        CheckConstraint("attempts >= 0", name="ck_graph_outbox_attempts"),
    )

    id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )
    aggregate_id: UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False, index=True))
    event_type: GraphEventType = Field(
        sa_column=Column(
            SAEnum(
                GraphEventType,
                name="graph_event_type",
                native_enum=False,
                length=32,
                values_callable=enum_values,
            )
        )
    )
    payload: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    status: OutboxStatus = Field(
        default=OutboxStatus.PENDING,
        sa_column=Column(
            SAEnum(
                OutboxStatus,
                name="outbox_status",
                native_enum=False,
                length=32,
                values_callable=enum_values,
            ),
            nullable=False,
        ),
    )
    attempts: int = Field(default=0, ge=0)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    published_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    last_error: str | None = Field(default=None, sa_column=Column(Text))
