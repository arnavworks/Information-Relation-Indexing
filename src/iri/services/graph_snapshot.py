"""Cross-store read model for the visual relational graph."""

from decimal import Decimal
from typing import Any, cast

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iri.api.schemas import (
    GraphAppearance,
    GraphConcept,
    GraphDataReference,
    GraphFact,
    GraphPoint,
    GraphSnapshotResponse,
)
from iri.db.models import DataReference, Fact, GranularPoint
from iri.graph.gateway import Neo4jConceptGateway


def _fact_value(fact: Fact) -> str:
    value: Decimal | Any | None = fact.numeric_value
    if value is None:
        value = fact.date_value
    if value is None:
        value = fact.text_value
    return str(value) if value is not None else ""


class GraphSnapshotService:
    def __init__(self, session: AsyncSession, graph: Neo4jConceptGateway) -> None:
        self._session = session
        self._graph = graph

    async def get(self) -> GraphSnapshotResponse:
        references = (
            (
                await self._session.execute(
                    select(DataReference).order_by(cast(Any, DataReference.id))
                )
            )
            .scalars()
            .all()
        )
        points = (
            (
                await self._session.execute(
                    select(GranularPoint).order_by(
                        cast(Any, GranularPoint.dri_id),
                        cast(Any, GranularPoint.page_start),
                        cast(Any, GranularPoint.point_number),
                    )
                )
            )
            .scalars()
            .all()
        )
        facts = (
            (
                await self._session.execute(
                    select(Fact).order_by(cast(Any, Fact.info_uid), cast(Any, Fact.name))
                )
            )
            .scalars()
            .all()
        )
        concepts = await anyio.to_thread.run_sync(self._graph.snapshot_concepts)

        return GraphSnapshotResponse(
            data_references=[
                GraphDataReference(
                    dri_id=reference.id,
                    dri_code=reference.reference_code,
                    source_name=reference.source_name,
                    source_type=reference.source_type,
                )
                for reference in references
                if reference.id is not None
            ],
            concepts=[
                GraphConcept(
                    info_uid=concept.info_uid,
                    name=concept.name,
                    summary_line_1=concept.summary_line_1,
                    summary_line_2=concept.summary_line_2,
                    appearances=[
                        GraphAppearance(
                            sinfo_uid=appearance.sinfo_uid,
                            dri_id=appearance.dri_id,
                            point_ids=list(appearance.point_ids),
                            coordinates=list(appearance.coordinates),
                            summary_line_1=appearance.summary_line_1,
                            summary_line_2=appearance.summary_line_2,
                        )
                        for appearance in concept.appearances
                    ],
                )
                for concept in concepts
            ],
            points=[
                GraphPoint(
                    point_id=point.id,
                    dri_id=point.dri_id,
                    coordinate=point.coordinate,
                    raw_text=point.raw_text,
                )
                for point in points
            ],
            facts=[
                GraphFact(
                    fact_id=fact.id,
                    info_uid=fact.info_uid,
                    source_point_id=fact.source_point_id,
                    name=fact.name,
                    value_type=fact.value_type,
                    value=_fact_value(fact),
                    unit=fact.unit,
                    currency=fact.currency,
                )
                for fact in facts
            ],
        )
