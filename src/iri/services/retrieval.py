"""Concept-first retrieval that emits only source-resolved evidence or facts."""

import json
from collections.abc import AsyncIterator
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import anyio

from iri.api.schemas import RetrievalMode, RetrievalRequest
from iri.embeddings.base import EmbeddingProvider
from iri.generation.base import (
    AnswerGenerationError,
    AnswerGenerator,
    GroundedAnswer,
    SourceExcerpt,
)
from iri.graph.gateway import Neo4jConceptGateway
from iri.repositories.postgres import ConceptMatch, RetrievalRepository


def _json_default(value: object) -> str:
    if isinstance(value, (UUID, date, datetime, Decimal)):
        return str(value)
    raise TypeError(f"Cannot JSON encode {type(value).__name__}")


def _line(event: str, payload: dict[str, Any]) -> bytes:
    """Encode one independently parseable NDJSON event."""

    return (
        json.dumps({"event": event, "data": payload}, default=_json_default, separators=(",", ":"))
        + "\n"
    ).encode()


class RetrievalService:
    def __init__(
        self,
        repository: RetrievalRepository,
        graph: Neo4jConceptGateway,
        embeddings: EmbeddingProvider,
        answerer: AnswerGenerator | None = None,
        answer_max_sources: int = 24,
    ) -> None:
        self._repository = repository
        self._graph = graph
        self._embeddings = embeddings
        self._answerer = answerer
        self._answer_max_sources = answer_max_sources

    async def prepare(self, request: RetrievalRequest) -> RetrievalRequest:
        """Resolve a missing query vector before streaming response headers."""

        if request.query_embedding is not None:
            return request
        embedding = await self._embeddings.embed_query(request.query)
        return request.model_copy(update={"query_embedding": embedding})

    async def stream(self, request: RetrievalRequest) -> AsyncIterator[bytes]:
        if request.query_embedding is None:
            raise RuntimeError("RetrievalRequest must be prepared before streaming")
        matches = await self._repository.nearest_concepts(
            request.query_embedding, request.concept_limit
        )
        yield _line("route", {"concepts": [self._match_payload(match) for match in matches]})
        yield _line(
            "stage",
            {"stage": "evidence", "message": "Resolving exact source coordinates"},
        )

        if request.mode is RetrievalMode.FACTS:
            facts = await self._repository.facts_for_concepts(
                [match.projection.info_uid for match in matches]
            )
            fact_points = await self._repository.points_by_ids(
                {fact.source_point_id for fact in facts}
            )
            point_by_id = {point.id: point for point in fact_points}
            sources: list[SourceExcerpt] = []
            for fact in facts:
                yield _line(
                    "fact",
                    {
                        "fact_id": fact.id,
                        "info_uid": fact.info_uid,
                        "source_point_id": fact.source_point_id,
                        "name": fact.name,
                        "value_type": fact.value_type,
                        "numeric_value": fact.numeric_value,
                        "date_value": fact.date_value,
                        "text_value": fact.text_value,
                        "unit": fact.unit,
                        "currency": fact.currency,
                        "as_of_date": fact.as_of_date,
                        "calculation_expression": fact.calculation_expression,
                        "input_fact_ids": fact.input_fact_ids,
                    },
                )
                point = point_by_id.get(fact.source_point_id)
                if point is not None and len(sources) < self._answer_max_sources:
                    value: object | None = fact.numeric_value
                    if value is None:
                        value = fact.date_value
                    if value is None:
                        value = fact.text_value
                    sources.append(
                        SourceExcerpt(
                            coordinate=point.coordinate,
                            text=f"{fact.name}: {value}"
                            f"{f' {fact.unit}' if fact.unit else ''}"
                            f"{f' {fact.currency}' if fact.currency else ''}. "
                            f"Source text: {point.raw_text}",
                        )
                    )
            async for event in self._answer_events(request.query, tuple(sources)):
                yield event
            yield _line("done", {"fact_count": len(facts), "evidence_count": 0})
            return

        point_ids: set[UUID] = set()
        bridges: list[dict[str, Any]] = []
        for match in matches:
            appearances = await anyio.to_thread.run_sync(
                self._graph.appearances_for, match.projection.info_uid
            )
            point_ids.update(point_id for item in appearances for point_id in item.point_ids)
            bridges.extend(
                {
                    "info_uid": match.projection.info_uid,
                    **asdict(appearance),
                }
                for appearance in appearances
            )

        points = await self._repository.points_by_ids(point_ids)
        bridges_by_point: dict[UUID, list[dict[str, Any]]] = {}
        for bridge in bridges:
            for point_id in bridge["point_ids"]:
                bridges_by_point.setdefault(point_id, []).append(bridge)
        sources = []
        for point in points:
            point_bridges = bridges_by_point.get(point.id, [])
            selected_bridge = point_bridges[0] if point_bridges else None
            yield _line(
                "evidence",
                {
                    "coordinate": point.coordinate,
                    "point_id": point.id,
                    "raw_text": point.raw_text,
                    "text_sha256": point.text_sha256,
                    "info_uid": selected_bridge["info_uid"] if selected_bridge else None,
                    "sinfo_uid": selected_bridge["sinfo_uid"] if selected_bridge else None,
                    "paths": [
                        {
                            "info_uid": item["info_uid"],
                            "sinfo_uid": item["sinfo_uid"],
                        }
                        for item in point_bridges
                    ],
                },
            )
            if len(sources) < self._answer_max_sources:
                sources.append(SourceExcerpt(coordinate=point.coordinate, text=point.raw_text))
        async for event in self._answer_events(request.query, tuple(sources)):
            yield event
        yield _line("done", {"fact_count": 0, "evidence_count": len(points)})

    async def _answer_events(
        self,
        query: str,
        sources: tuple[SourceExcerpt, ...],
    ) -> AsyncIterator[bytes]:
        if not sources:
            yield _line(
                "answer",
                {
                    "text": "No source-resolved evidence was found for this question.",
                    "citations": [],
                    "model": None,
                    "grounded": True,
                    "generated": False,
                },
            )
            return
        yield _line(
            "stage",
            {"stage": "synthesis", "message": "Synthesizing a grounded answer with Gemini"},
        )
        if self._answerer is None:
            fallback = self._extractive_fallback(sources, "Answer generation is not configured")
            yield _line(
                "answer",
                {
                    "text": fallback.text,
                    "citations": list(fallback.citations),
                    "model": None,
                    "grounded": True,
                    "generated": False,
                },
            )
            return
        try:
            answer = await self._answerer.generate(query, sources)
        except AnswerGenerationError as exc:
            fallback = self._extractive_fallback(sources, str(exc))
            yield _line(
                "answer",
                {
                    "text": fallback.text,
                    "citations": list(fallback.citations),
                    "model": None,
                    "grounded": True,
                    "generated": False,
                },
            )
            return
        yield _line(
            "stage",
            {"stage": "validation", "message": "Validating every DRI citation"},
        )
        yield _line(
            "answer",
            {
                "text": answer.text,
                "citations": list(answer.citations),
                "model": answer.model,
                "grounded": True,
                "generated": True,
            },
        )

    @staticmethod
    def _extractive_fallback(
        sources: tuple[SourceExcerpt, ...],
        reason: str,
    ) -> GroundedAnswer:
        selected: list[SourceExcerpt] = []
        seen: set[str] = set()
        for source in sources:
            if source.coordinate in seen:
                continue
            seen.add(source.coordinate)
            selected.append(source)
            if len(selected) == 3:
                break
        excerpts = []
        for source in selected:
            normalized = " ".join(source.text.split())
            excerpt = normalized[:320]
            if len(normalized) > len(excerpt):
                excerpt = f"{excerpt.rstrip()}…"
            excerpts.append(f"- [{source.coordinate}] {excerpt}")
        text = (
            f"Gemini synthesis is temporarily unavailable ({reason}). "
            "The following source-resolved evidence was retrieved:\n\n"
            + "\n\n".join(excerpts)
        )
        return GroundedAnswer(
            text=text,
            citations=tuple(source.coordinate for source in selected),
            model="extractive-fallback",
        )

    @staticmethod
    def _match_payload(match: ConceptMatch) -> dict[str, Any]:
        projection = match.projection
        return {
            "info_uid": projection.info_uid,
            "summary_line_1": projection.summary_line_1,
            "summary_line_2": projection.summary_line_2,
            "cosine_distance": match.cosine_distance,
            "summary_version": projection.summary_version,
        }
