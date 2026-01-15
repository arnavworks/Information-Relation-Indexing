from iri.extraction.files import extract_point_candidates
from iri.extraction.gemini import deterministic_fallback


def test_text_source_becomes_auditable_points(tmp_path) -> None:
    source = tmp_path / "policy.txt"
    source.write_text(
        "Employees retain ownership of pre-existing intellectual property.\n\n"
        "Work created within assigned duties belongs to the company under the IP policy."
    )

    points = extract_point_candidates(source)

    assert [point.reference for point in points] == ["P1.1", "P1.2"]
    assert "pre-existing intellectual property" in points[0].text


def test_deterministic_fallback_keeps_exact_point_references(tmp_path) -> None:
    source = tmp_path / "policy.md"
    source.write_text("The retention period is seven years. This applies to regulated records.")
    points = extract_point_candidates(source)

    extracted = deterministic_fallback(points)

    assert extracted.concepts
    assert extracted.concepts[0].point_refs == [points[0].reference]
