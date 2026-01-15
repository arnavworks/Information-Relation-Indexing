"""Background ingestion pipeline that materializes the five DRI layers."""

import asyncio
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

import anyio
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from iri.core.config import get_settings
from iri.db.models import (
    ConceptSearchProjection,
    DataReference,
    Fact,
    FactValueType,
    GranularPoint,
    GraphEventType,
    GraphProjectionOutbox,
    IngestionJob,
    IngestionStatus,
    OutboxStatus,
    utc_now,
)
from iri.db.session import session_factory
from iri.embeddings.gemini import GeminiEmbeddingProvider
from iri.extraction.files import PointCandidate, extract_point_candidates
from iri.extraction.gemini import ExtractedInformation, GeminiExtractionAgent
from iri.graph.gateway import AppearanceWrite, ConceptWrite, Neo4jConceptGateway

_PROCESSING_LIMIT = asyncio.Semaphore(2)
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


def _concept_uuid(name: str) -> UUID:
    normalized = " ".join(re.sub(r"[^a-z0-9 ]+", " ", name.casefold()).split())
    return uuid5(NAMESPACE_URL, f"iri:concept:{normalized}")


def _appearance_uuid(info_uid: UUID, dri_id: int) -> UUID:
    return uuid5(NAMESPACE_URL, f"iri:appearance:{info_uid}:{dri_id}")


def _parse_fact_value(value_type: str, raw: str) -> dict[str, Any] | None:
    if value_type == "number":
        cleaned = re.sub(r"[^0-9.\-]", "", raw.replace(",", ""))
        try:
            return {"value_type": FactValueType.NUMBER, "numeric_value": Decimal(cleaned)}
        except InvalidOperation:
            return None
    if value_type == "date":
        try:
            return {"value_type": FactValueType.DATE, "date_value": date.fromisoformat(raw)}
        except ValueError:
            return {"value_type": FactValueType.TEXT, "text_value": raw}
    return {"value_type": FactValueType.TEXT, "text_value": raw}


class IngestionProcessor:
    def __init__(self) -> None:
        settings = get_settings()
        self._extractor = GeminiExtractionAgent(settings.gemini_api_key, settings.extraction_model)
        self._embeddings = GeminiEmbeddingProvider(
            settings.gemini_api_key, settings.embedding_model
        )
        self._graph = Neo4jConceptGateway()

    async def process(self, job_id: UUID, file_path: Path) -> None:
        try:
            await self._set_status(job_id, IngestionStatus.PROCESSING)
            candidates = await anyio.to_thread.run_sync(extract_point_candidates, file_path)
            if not candidates:
                raise ValueError("No extractable text was found in the uploaded source")
            source_name, dri_id = await self._job_source(job_id)
            extracted = await self._extractor.extract(source_name, candidates)
            writes, event_ids, info_uids = await self._persist(
                job_id, dri_id, candidates, extracted
            )
            await anyio.to_thread.run_sync(self._graph.upsert_extraction, writes)
            await self._publish(job_id, event_ids, info_uids)
        except Exception as exc:
            await self._set_status(
                job_id,
                IngestionStatus.FAILED,
                error_code="extraction_failed",
                error_detail=str(exc)[:2_000],
            )
        finally:
            await self._embeddings.aclose()

    async def _job_source(self, job_id: UUID) -> tuple[str, int]:
        async with session_factory() as session:
            job = await session.get(IngestionJob, job_id)
            if job is None:
                raise LookupError(f"Unknown ingestion job {job_id}")
            reference = await session.get(DataReference, job.dri_id)
            if reference is None:
                raise LookupError(f"Missing DRI{job.dri_id}")
            return reference.source_name, job.dri_id

    async def _set_status(
        self,
        job_id: UUID,
        status: IngestionStatus,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        async with session_factory() as session:
            job = await session.get(IngestionJob, job_id)
            if job is None:
                return
            job.status = status
            job.error_code = error_code
            job.error_detail = error_detail
            if status is IngestionStatus.PROCESSING:
                job.started_at = utc_now()
            if status in {IngestionStatus.COMPLETE, IngestionStatus.FAILED}:
                job.completed_at = utc_now()
            await session.commit()

    async def _persist(
        self,
        job_id: UUID,
        dri_id: int,
        candidates: tuple[PointCandidate, ...],
        extracted: ExtractedInformation,
    ) -> tuple[tuple[ConceptWrite, ...], tuple[UUID, ...], tuple[UUID, ...]]:
        async with session_factory() as session:
            existing_points = (
                (
                    await session.execute(
                        select(GranularPoint).where(cast(Any, GranularPoint.dri_id) == dri_id)
                    )
                )
                .scalars()
                .all()
            )
            points_by_ref: dict[str, GranularPoint] = {
                f"P{point.page_start}.{point.point_number}": point for point in existing_points
            }
            for candidate in candidates:
                if candidate.reference in points_by_ref:
                    continue
                point = GranularPoint(
                    dri_id=dri_id,
                    page_start=candidate.page,
                    page_end=candidate.page,
                    point_number=candidate.point_number,
                    raw_text=candidate.text,
                    text_sha256=sha256(candidate.text.encode()).hexdigest(),
                    extraction_version="gemini-structured-v1",
                )
                session.add(point)
                points_by_ref[candidate.reference] = point
            await session.flush()

            concept_writes: list[ConceptWrite] = []
            event_ids: list[UUID] = []
            info_uids: list[UUID] = []
            concept_name_map: dict[str, UUID] = {}
            projection_table = cast(Any, ConceptSearchProjection).__table__
            for concept in extracted.concepts:
                valid_refs = [ref for ref in concept.point_refs if ref in points_by_ref]
                if not valid_refs:
                    continue
                info_uid = _concept_uuid(concept.name)
                concept_name_map[concept.name.casefold()] = info_uid
                info_uids.append(info_uid)
                embedding = await self._embeddings.embed_document(
                    concept.name,
                    f"{concept.summary_line_1}\n{concept.summary_line_2}",
                )
                await session.execute(
                    pg_insert(projection_table)
                    .values(
                        info_uid=info_uid,
                        summary_line_1=concept.summary_line_1,
                        summary_line_2=concept.summary_line_2,
                        embedding=embedding,
                        embedding_model=get_settings().embedding_model,
                        summary_version=1,
                        is_routable=False,
                        indexed_at=utc_now(),
                    )
                    .on_conflict_do_update(
                        index_elements=[projection_table.c.info_uid],
                        set_={
                            "summary_line_1": concept.summary_line_1,
                            "summary_line_2": concept.summary_line_2,
                            "embedding": embedding,
                            "embedding_model": get_settings().embedding_model,
                            "indexed_at": utc_now(),
                        },
                    )
                )
                sinfo_uid = _appearance_uuid(info_uid, dri_id)
                appearance = AppearanceWrite(
                    sinfo_uid=sinfo_uid,
                    dri_id=dri_id,
                    point_ids=tuple(points_by_ref[ref].id for ref in valid_refs),
                    coordinates=tuple(points_by_ref[ref].coordinate for ref in valid_refs),
                    summary_line_1=concept.summary_line_1,
                    summary_line_2=concept.summary_line_2,
                )
                concept_writes.append(
                    ConceptWrite(
                        info_uid=info_uid,
                        name=concept.name,
                        summary_line_1=concept.summary_line_1,
                        summary_line_2=concept.summary_line_2,
                        appearances=(appearance,),
                    )
                )
                for event_type, payload in (
                    (
                        GraphEventType.CONCEPT_UPSERT,
                        {"info_uid": str(info_uid), "name": concept.name},
                    ),
                    (
                        GraphEventType.APPEARANCE_UPSERT,
                        {"info_uid": str(info_uid), "sinfo_uid": str(sinfo_uid)},
                    ),
                ):
                    event = GraphProjectionOutbox(
                        aggregate_id=info_uid,
                        event_type=event_type,
                        payload=payload,
                    )
                    session.add(event)
                    event_ids.append(event.id)

            for extracted_fact in extracted.facts:
                fact_info_uid = concept_name_map.get(extracted_fact.concept_name.casefold())
                fact_point = points_by_ref.get(extracted_fact.point_ref)
                values = _parse_fact_value(extracted_fact.value_type, extracted_fact.value)
                if fact_info_uid is None or fact_point is None or values is None:
                    continue
                duplicate = (
                    await session.execute(
                        select(Fact).where(
                            cast(Any, Fact.info_uid) == fact_info_uid,
                            cast(Any, Fact.name) == extracted_fact.name,
                            cast(Any, Fact.source_point_id) == fact_point.id,
                        )
                    )
                ).scalar_one_or_none()
                if duplicate is None:
                    session.add(
                        Fact(
                            info_uid=fact_info_uid,
                            source_point_id=fact_point.id,
                            name=extracted_fact.name,
                            unit=extracted_fact.unit,
                            currency=extracted_fact.currency,
                            **values,
                        )
                    )
            await session.commit()
            return tuple(concept_writes), tuple(event_ids), tuple(dict.fromkeys(info_uids))

    async def _publish(
        self, job_id: UUID, event_ids: tuple[UUID, ...], info_uids: tuple[UUID, ...]
    ) -> None:
        async with session_factory() as session:
            if event_ids:
                events = (
                    (
                        await session.execute(
                            select(GraphProjectionOutbox).where(
                                cast(Any, GraphProjectionOutbox.id).in_(event_ids)
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for event in events:
                    event.status = OutboxStatus.PUBLISHED
                    event.published_at = utc_now()
                    event.attempts += 1
            if info_uids:
                projections = (
                    (
                        await session.execute(
                            select(ConceptSearchProjection).where(
                                cast(Any, ConceptSearchProjection.info_uid).in_(info_uids)
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for projection in projections:
                    projection.is_routable = True
            job = await session.get(IngestionJob, job_id)
            if job is not None:
                job.status = IngestionStatus.COMPLETE
                job.completed_at = utc_now()
            await session.commit()


async def process_ingestion(job_id: UUID, file_path: Path) -> None:
    async with _PROCESSING_LIMIT:
        await IngestionProcessor().process(job_id, file_path)


def schedule_ingestion(job_id: UUID, file_path: Path) -> None:
    """Schedule local worker execution while retaining a strong task reference."""

    task = asyncio.create_task(process_ingestion(job_id, file_path))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
