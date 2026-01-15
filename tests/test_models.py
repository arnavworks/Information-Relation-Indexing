from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from iri.api.schemas import FactCreate
from iri.db.models import FactValueType, GranularPoint


def test_granular_point_renders_canonical_coordinate() -> None:
    point = GranularPoint(
        dri_id=7,
        page_start=12,
        page_end=14,
        point_number=3,
        raw_text="Auditable evidence.",
        text_sha256="a" * 64,
    )

    assert point.coordinate == "DRI7.12-14.3"


def test_fact_contract_accepts_one_matching_numeric_value() -> None:
    fact = FactCreate(
        info_uid=uuid4(),
        source_point_id=uuid4(),
        name="Annual revenue",
        value_type=FactValueType.NUMBER,
        numeric_value=Decimal("1250000.25"),
    )

    assert fact.numeric_value == Decimal("1250000.25")


def test_fact_contract_rejects_mismatched_value_type() -> None:
    with pytest.raises(ValidationError, match="date facts require date_value"):
        FactCreate(
            info_uid=uuid4(),
            source_point_id=uuid4(),
            name="Effective date",
            value_type=FactValueType.DATE,
            numeric_value=Decimal("2026"),
        )


def test_fact_contract_accepts_date() -> None:
    fact = FactCreate(
        info_uid=uuid4(),
        source_point_id=uuid4(),
        name="Effective date",
        value_type=FactValueType.DATE,
        date_value=date(2026, 7, 4),
    )
    assert fact.date_value == date(2026, 7, 4)
