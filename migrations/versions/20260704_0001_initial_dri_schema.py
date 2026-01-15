"""Create the physical DRI ledger, evidence points, fact sheet, and concept index."""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260704_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The extension must exist before SQLAlchemy compiles the VECTOR column.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "data_references",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("immutable_uid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=False),
        sa.Column("source_name", sa.String(length=512), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
        sa.Column(
            "source_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("char_length(content_sha256) = 64", name="ck_dri_sha256_length"),
        sa.CheckConstraint(
            "source_type IN ('pdf','document','spreadsheet','json','database','stream','other')",
            name="ck_dri_source_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_sha256", "source_uri", name="uq_dri_content_source"),
        sa.UniqueConstraint("immutable_uid"),
    )
    op.create_index("ix_data_references_content_sha256", "data_references", ["content_sha256"])

    op.create_table(
        "granular_points",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dri_id", sa.BigInteger(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("point_number", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("extraction_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("page_start > 0", name="ck_point_page_start_positive"),
        sa.CheckConstraint("page_end >= page_start", name="ck_point_page_order"),
        sa.CheckConstraint("point_number > 0", name="ck_point_number_positive"),
        sa.CheckConstraint("char_start IS NULL OR char_start >= 0", name="ck_point_char_start"),
        sa.CheckConstraint(
            "char_end IS NULL OR (char_start IS NOT NULL AND char_end > char_start)",
            name="ck_point_char_order",
        ),
        sa.ForeignKeyConstraint(["dri_id"], ["data_references.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dri_id", "page_start", "page_end", "point_number", name="uq_point_coordinate"
        ),
    )
    op.create_index("ix_granular_points_dri_id", "granular_points", ["dri_id"])

    op.create_table(
        "concept_search_projections",
        sa.Column("info_uid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("summary_line_1", sa.String(length=1000), nullable=False),
        sa.Column("summary_line_2", sa.String(length=1000), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.VECTOR(dim=1536), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("summary_version", sa.Integer(), nullable=False),
        sa.Column("is_routable", sa.Boolean(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("info_uid"),
    )
    op.create_index(
        "ix_concept_embedding_hnsw_cosine",
        "concept_search_projections",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_concept_search_projections_is_routable",
        "concept_search_projections",
        ["is_routable"],
    )

    op.create_table(
        "facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("info_uid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_point_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("value_type", sa.String(length=32), nullable=False),
        sa.Column("numeric_value", sa.Numeric(precision=38, scale=12), nullable=True),
        sa.Column("date_value", sa.Date(), nullable=True),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=100), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("calculation_expression", sa.Text(), nullable=True),
        sa.Column(
            "input_fact_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(value_type IN ('number', 'calculation') AND numeric_value IS NOT NULL "
            "AND date_value IS NULL AND text_value IS NULL) OR "
            "(value_type = 'date' AND date_value IS NOT NULL "
            "AND numeric_value IS NULL AND text_value IS NULL) OR "
            "(value_type = 'text' AND text_value IS NOT NULL "
            "AND numeric_value IS NULL AND date_value IS NULL)",
            name="ck_fact_typed_value",
        ),
        sa.CheckConstraint(
            "value_type != 'calculation' OR calculation_expression IS NOT NULL",
            name="ck_fact_calculation_expression",
        ),
        sa.CheckConstraint(
            "value_type IN ('number','date','text','calculation')", name="ck_fact_value_type"
        ),
        sa.ForeignKeyConstraint(["source_point_id"], ["granular_points.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("info_uid", "name", "source_point_id", name="uq_fact_origin"),
    )
    op.create_index("ix_facts_info_uid", "facts", ["info_uid"])
    op.create_index("ix_facts_source_point_id", "facts", ["source_point_id"])

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dri_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('registered','queued','processing','complete','failed')",
            name="ck_ingestion_status",
        ),
        sa.ForeignKeyConstraint(["dri_id"], ["data_references.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_ingestion_jobs_dri_id", "ingestion_jobs", ["dri_id"])

    op.create_table(
        "graph_projection_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint("attempts >= 0", name="ck_graph_outbox_attempts"),
        sa.CheckConstraint(
            "event_type IN ('concept_upsert','appearance_upsert','hierarchy_upsert')",
            name="ck_graph_outbox_event_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending','published','failed')", name="ck_graph_outbox_status"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_graph_projection_outbox_aggregate_id",
        "graph_projection_outbox",
        ["aggregate_id"],
    )
    op.create_index(
        "ix_graph_outbox_pending",
        "graph_projection_outbox",
        ["status", "created_at"],
    )

    op.execute(
        """
        CREATE FUNCTION continuum_reject_ledger_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Continuum DRI ledger rows are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table_name in ("data_references", "granular_points"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_append_only
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION continuum_reject_ledger_mutation()
            """
        )


def downgrade() -> None:
    for table_name in ("data_references", "granular_points"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name}")
    op.execute("DROP FUNCTION IF EXISTS continuum_reject_ledger_mutation()")
    op.drop_table("graph_projection_outbox")
    op.drop_table("ingestion_jobs")
    op.drop_table("facts")
    op.drop_index("ix_concept_embedding_hnsw_cosine", table_name="concept_search_projections")
    op.drop_table("concept_search_projections")
    op.drop_table("granular_points")
    op.drop_table("data_references")
    # Do not drop the shared vector extension; other schemas may depend on it.
