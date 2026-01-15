"""Provider-neutral contracts for evidence-grounded answer generation."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SourceExcerpt:
    coordinate: str
    text: str


@dataclass(frozen=True, slots=True)
class GroundedAnswer:
    text: str
    citations: tuple[str, ...]
    model: str


class AnswerGenerationError(RuntimeError):
    """Raised when a grounded answer cannot be produced safely."""


class AnswerGenerator(Protocol):
    async def generate(
        self,
        query: str,
        sources: tuple[SourceExcerpt, ...],
    ) -> GroundedAnswer: ...
