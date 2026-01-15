"""Focused PostgreSQL repositories for ingestion and deterministic retrieval."""

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from iri.db.models import (
    ConceptSearchProjection,
    DataReference,
    Fact,
    GranularPoint,
    IngestionJob,
)


@dataclass(frozen=True, slots=True)
class ConceptMatch:
    projection: ConceptSearchProjection
    cosine_distance: float


class IngestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_job_by_idempotency_key(self, key: str) -> IngestionJob | None:
        idempotency_column = cast(Any, IngestionJob.idempotency_key)
        statement = select(IngestionJob).where(idempotency_column == key)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def add_reference_and_job(
        self, reference: DataReference, job: IngestionJob
    ) -> tuple[DataReference, IngestionJob]:
        # PostgreSQL arbitrates concurrent registration of the same physical
        # source. ON CONFLICT avoids a check-then-insert race on the DRI ledger.
        table = cast(Any, DataReference).__table__
        insert_reference = (
            pg_insert(table)
            .values(
                immutable_uid=reference.immutable_uid,
                source_type=reference.source_type,
                source_uri=reference.source_uri,
                source_name=reference.source_name,
                media_type=reference.media_type,
                content_sha256=reference.content_sha256,
                byte_size=reference.byte_size,
                source_metadata=reference.source_metadata,
                registered_at=reference.registered_at,
            )
            .on_conflict_do_nothing(constraint="uq_dri_content_source")
            .returning(table.c.id)
        )
        dri_id = (await self._session.execute(insert_reference)).scalar_one_or_none()
        if dri_id is None:
            source_uri_column = cast(Any, DataReference.source_uri)
            content_hash_column = cast(Any, DataReference.content_sha256)
            existing_reference = (
                await self._session.execute(
                    select(DataReference).where(
                        source_uri_column == reference.source_uri,
                        content_hash_column == reference.content_sha256,
                    )
                )
            ).scalar_one()
            reference = existing_reference
            dri_id = existing_reference.id
        else:
            reference.id = int(dri_id)

        if dri_id is None:
            raise RuntimeError("PostgreSQL did not assign a DRI identifier")
        job.dri_id = int(dri_id)
        self._session.add(job)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            # A concurrent request may have won the idempotency-key race. Roll
            # back the whole transaction (including a newly inserted DRI row)
            # and return the committed winner. Any other constraint still raises.
            await self._session.rollback()
            existing_job = await self.find_job_by_idempotency_key(job.idempotency_key)
            if existing_job is None:
                raise
            conflict_reference = await self._session.get(DataReference, existing_job.dri_id)
            if conflict_reference is None:
                raise RuntimeError("Idempotent ingestion points to a missing DRI") from exc
            return conflict_reference, existing_job

        await self._session.refresh(job)
        return reference, job

    async def get_job(self, job_id: UUID) -> IngestionJob | None:
        return await self._session.get(IngestionJob, job_id)


class RetrievalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def nearest_concepts(
        self, embedding: list[float], limit: int
    ) -> tuple[ConceptMatch, ...]:
        vector_column = cast(Any, ConceptSearchProjection.embedding)
        routable_column = cast(Any, ConceptSearchProjection.is_routable)
        distance = vector_column.cosine_distance(embedding).label("cosine_distance")
        statement = (
            select(ConceptSearchProjection, distance)
            .where(routable_column.is_(True))
            .order_by(distance)
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return tuple(ConceptMatch(row[0], float(row[1])) for row in rows)

    async def points_by_ids(self, point_ids: set[UUID]) -> tuple[GranularPoint, ...]:
        if not point_ids:
            return ()
        point_id_column = cast(Any, GranularPoint.id)
        statement = (
            select(GranularPoint)
            .where(point_id_column.in_(point_ids))
            .order_by(
                cast(Any, GranularPoint.dri_id),
                cast(Any, GranularPoint.page_start),
                cast(Any, GranularPoint.page_end),
                cast(Any, GranularPoint.point_number),
            )
        )
        return tuple((await self._session.execute(statement)).scalars().all())

    async def facts_for_concepts(self, info_uids: list[UUID]) -> tuple[Fact, ...]:
        if not info_uids:
            return ()
        info_uid_column = cast(Any, Fact.info_uid)
        statement = (
            select(Fact)
            .where(info_uid_column.in_(info_uids))
            .order_by(info_uid_column, cast(Any, Fact.name))
        )
        return tuple((await self._session.execute(statement)).scalars().all())
