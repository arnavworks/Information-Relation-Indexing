"""Gemini structured extraction constrained to pre-identified source points."""

import re
from collections.abc import Sequence

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, SecretStr

from iri.extraction.files import PointCandidate


class ExtractedFact(BaseModel):
    concept_name: str
    point_ref: str
    name: str
    value_type: str = Field(pattern="^(number|date|text)$")
    value: str
    unit: str | None = None
    currency: str | None = None


class ExtractedConcept(BaseModel):
    name: str
    summary_line_1: str
    summary_line_2: str
    point_refs: list[str] = Field(min_length=1)


class ExtractedInformation(BaseModel):
    concepts: list[ExtractedConcept]
    facts: list[ExtractedFact] = Field(default_factory=list)


def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+", text) if item.strip()]


def deterministic_fallback(points: Sequence[PointCandidate]) -> ExtractedInformation:
    concepts: list[ExtractedConcept] = []
    for point in points[:8]:
        sentences = _sentences(point.text)
        first = sentences[0][:500] if sentences else point.text[:500]
        second = (
            sentences[1][:500]
            if len(sentences) > 1
            else f"Supported by source point {point.reference}."
        )
        name = " ".join(re.sub(r"[^A-Za-z0-9 ]+", " ", first).split()[:10]) or point.reference
        concepts.append(
            ExtractedConcept(
                name=name,
                summary_line_1=first,
                summary_line_2=second,
                point_refs=[point.reference],
            )
        )
    return ExtractedInformation(concepts=concepts)


class GeminiExtractionAgent:
    def __init__(self, api_key: SecretStr | None, model: str) -> None:
        self._api_key = api_key
        self._model = model

    async def extract(
        self, source_name: str, points: Sequence[PointCandidate]
    ) -> ExtractedInformation:
        if not points:
            return ExtractedInformation(concepts=[])
        if self._api_key is None or not self._api_key.get_secret_value():
            return deterministic_fallback(points)

        allowed = {point.reference for point in points}
        corpus = "\n\n".join(f"[{point.reference}] {point.text}" for point in points)
        prompt = f"""Extract the unique enterprise concepts and explicit facts from {source_name}.

Rules:
- Return at most 12 concepts and only material concepts supported by the numbered points.
- Each concept must have exactly two concise, detailed summary lines.
- point_refs and fact point_ref values MUST be chosen from the supplied [P#.#] references.
- Facts must be explicit values or dates present in their source point. Never calculate or infer.
- Reuse the same normalized concept_name in facts.

SOURCE POINTS:
{corpus}
"""
        client = genai.Client(api_key=self._api_key.get_secret_value())
        try:
            response = await client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=ExtractedInformation.model_json_schema(),
                    temperature=0,
                ),
            )
            extracted = ExtractedInformation.model_validate_json(response.text or "{}")
        except Exception:
            return deterministic_fallback(points)
        finally:
            await client.aio.aclose()
            client.close()

        valid_concepts = [
            concept
            for concept in extracted.concepts[:12]
            if concept.point_refs and set(concept.point_refs) <= allowed
        ]
        concept_names = {concept.name.casefold() for concept in valid_concepts}
        valid_facts = [
            fact
            for fact in extracted.facts
            if fact.point_ref in allowed and fact.concept_name.casefold() in concept_names
        ]
        if not valid_concepts:
            return deterministic_fallback(points)
        return ExtractedInformation(concepts=valid_concepts, facts=valid_facts)
