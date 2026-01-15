from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from iri.generation.base import (
    AnswerGenerationError,
    GroundedAnswer,
    SourceExcerpt,
)
from iri.generation.gemini import GeneratedAnswerDraft, validate_grounded_answer
from iri.services.retrieval import RetrievalService


class StubAnswerGenerator:
    async def generate(
        self, query: str, sources: tuple[SourceExcerpt, ...]
    ) -> GroundedAnswer:
        assert query == "Who owns customer data?"
        assert sources[0].coordinate == "DRI20.5-5.1"
        return GroundedAnswer(
            text="The customer owns customer data. [DRI20.5-5.1]",
            citations=("DRI20.5-5.1",),
            model="gemini-test",
        )


class RateLimitedAnswerGenerator:
    async def generate(
        self, query: str, sources: tuple[SourceExcerpt, ...]
    ) -> GroundedAnswer:
        raise AnswerGenerationError("Gemini answer quota remained exhausted after retrying")


def test_grounded_answer_accepts_only_retrieved_inline_citations() -> None:
    answer = validate_grounded_answer(
        GeneratedAnswerDraft(
            answer="The customer owns customer data. [DRI20.5-5.1]",
            citations=["DRI20.5-5.1"],
        ),
        ("DRI20.5-5.1", "DRI12.3-3.1"),
        "gemini-test",
    )

    assert answer.citations == ("DRI20.5-5.1",)
    assert answer.model == "gemini-test"


def test_grounded_answer_rejects_invented_coordinate() -> None:
    with pytest.raises(AnswerGenerationError, match="outside the retrieved evidence"):
        validate_grounded_answer(
            GeneratedAnswerDraft(
                answer="The customer owns customer data. [DRI999.1-1.1]",
                citations=["DRI999.1-1.1"],
            ),
            ("DRI20.5-5.1",),
            "gemini-test",
        )


def test_grounded_answer_requires_inline_citation() -> None:
    with pytest.raises(AnswerGenerationError, match="inline DRI citation"):
        validate_grounded_answer(
            GeneratedAnswerDraft(
                answer="The customer owns customer data.",
                citations=["DRI20.5-5.1"],
            ),
            ("DRI20.5-5.1",),
            "gemini-test",
        )


def test_retrieval_stream_emits_synthesis_validation_and_answer() -> None:
    service = RetrievalService(Any, Any, Any, StubAnswerGenerator())  # type: ignore[arg-type]

    async def collect() -> list[dict[str, object]]:
        return [
            json.loads(event)
            async for event in service._answer_events(
                "Who owns customer data?",
                (SourceExcerpt("DRI20.5-5.1", "Customer retains ownership."),),
            )
        ]

    events = asyncio.run(collect())

    assert [event["event"] for event in events] == ["stage", "stage", "answer"]
    assert events[-1]["data"] == {
        "text": "The customer owns customer data. [DRI20.5-5.1]",
        "citations": ["DRI20.5-5.1"],
        "model": "gemini-test",
        "grounded": True,
        "generated": True,
    }


def test_retrieval_stream_returns_cited_fallback_when_generation_is_rate_limited() -> None:
    service = RetrievalService(  # type: ignore[arg-type]
        Any,
        Any,
        Any,
        RateLimitedAnswerGenerator(),
    )

    async def collect() -> list[dict[str, object]]:
        return [
            json.loads(event)
            async for event in service._answer_events(
                "Who owns customer data?",
                (SourceExcerpt("DRI20.5-5.1", "Customer retains ownership."),),
            )
        ]

    answer = asyncio.run(collect())[-1]["data"]
    assert isinstance(answer, dict)
    assert answer["generated"] is False
    assert answer["grounded"] is True
    assert answer["citations"] == ["DRI20.5-5.1"]
