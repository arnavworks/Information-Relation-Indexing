from uuid import uuid4

import pytest
from pydantic import ValidationError

from iri.domain.extraction import (
    AppearanceDraft,
    ConceptDraft,
    ExtractionBundle,
    PointDraft,
)


def test_bundle_rejects_dangling_appearance_point() -> None:
    info_uid = uuid4()
    with pytest.raises(ValidationError, match="unknown point local_key"):
        ExtractionBundle(
            dri_id=1,
            extraction_version="extractor-1",
            agent_id="agent-a",
            points=(
                PointDraft(
                    local_key="p1",
                    page_start=1,
                    page_end=1,
                    point_number=1,
                    raw_text="Evidence",
                ),
            ),
            concepts=(
                ConceptDraft(
                    info_uid=info_uid,
                    name="Policy",
                    summary_line_1="The policy defines ownership.",
                    summary_line_2="It applies to employee-created intellectual property.",
                ),
            ),
            appearances=(
                AppearanceDraft(
                    info_uid=info_uid,
                    point_local_keys=("missing",),
                    source_summary_line_1="The source defines ownership.",
                    source_summary_line_2="The cited clause states its scope.",
                ),
            ),
        )
