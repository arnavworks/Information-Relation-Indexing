"""Deterministic extraction of candidate evidence points from uploaded files."""

import json
import re
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass(frozen=True, slots=True)
class PointCandidate:
    reference: str
    page: int
    point_number: int
    text: str


def _paragraphs(text: str) -> list[str]:
    normalized = text.replace("\x00", " ").replace("\r\n", "\n")
    blocks = [re.sub(r"\s+", " ", block).strip() for block in re.split(r"\n\s*\n", normalized)]
    blocks = [block for block in blocks if len(block) >= 30]
    if blocks:
        return blocks
    # OCR and generated PDFs often contain no blank lines. Sentence-aware chunks
    # retain exact source text while preventing one enormous evidence point.
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", normalized).strip())
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) > 900 and current:
            chunks.append(current)
            current = ""
        current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if len(chunk) >= 30]


def _pages(path: Path) -> list[str]:
    extension = path.suffix.lower()
    if extension == ".pdf":
        return [(page.extract_text() or "") for page in PdfReader(path).pages]
    raw = path.read_text(encoding="utf-8", errors="replace")
    if extension == ".json":
        with suppress(json.JSONDecodeError):
            raw = json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
    return [raw]


def extract_point_candidates(path: Path, limit: int = 60) -> tuple[PointCandidate, ...]:
    candidates: list[PointCandidate] = []
    for page_number, page_text in enumerate(_pages(path), start=1):
        for point_number, paragraph in enumerate(_paragraphs(page_text), start=1):
            candidates.append(
                PointCandidate(
                    reference=f"P{page_number}.{point_number}",
                    page=page_number,
                    point_number=point_number,
                    text=paragraph[:2_500],
                )
            )
            if len(candidates) >= limit:
                return tuple(candidates)
    return tuple(candidates)
