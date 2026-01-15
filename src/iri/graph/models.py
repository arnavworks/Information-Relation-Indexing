"""Neomodel schema for canonical concepts and their source appearances.

The graph stores routing topology and PostgreSQL identifiers only. Raw source
text and typed fact values stay in PostgreSQL so an answer has one evidence
authority and one transactional audit trail.
"""

from neomodel.properties import (
    ArrayProperty,
    DateTimeProperty,
    IntegerProperty,
    StringProperty,
    UniqueIdProperty,
)
from neomodel.sync_.cardinality import One, ZeroOrMore  # type: ignore[attr-defined]
from neomodel.sync_.node import StructuredNode
from neomodel.sync_.relationship import StructuredRel
from neomodel.sync_.relationship_manager import RelationshipFrom, RelationshipTo


class AppearanceRelationship(StructuredRel):
    """The ``sinfo_uid`` directional bridge from concept to occurrence."""

    sinfo_uid = StringProperty(required=True, unique_index=True)
    linked_at = DateTimeProperty(default_now=True)
    extraction_version = StringProperty(default="1")


class ConceptHierarchyRelationship(StructuredRel):
    """Auditable declaration that one concept contains a narrower concept."""

    rationale = StringProperty(required=True)
    created_at = DateTimeProperty(default_now=True)


class InfoAppearanceNode(StructuredNode):
    """One source-specific expression of an otherwise deduplicated concept."""

    sinfo_uid = UniqueIdProperty()
    dri_id = IntegerProperty(required=True, index=True)
    # UUID strings point to granular_points.id; coordinates aid graph inspection
    # but PostgreSQL remains authoritative for both coordinates and raw text.
    point_ids = ArrayProperty(StringProperty(), required=True)
    coordinates = ArrayProperty(StringProperty(), required=True)
    source_summary_line_1 = StringProperty(required=True)
    source_summary_line_2 = StringProperty(required=True)
    created_at = DateTimeProperty(default_now=True)

    concept = RelationshipFrom(
        "InfoUIDNode",
        "APPEARS_AS",
        model=AppearanceRelationship,
        cardinality=One,
    )


class InfoUIDNode(StructuredNode):
    """Canonical, deduplicated information identity—the reasoning graph root."""

    info_uid = UniqueIdProperty()
    name = StringProperty(required=True, index=True)
    summary_line_1 = StringProperty(required=True)
    summary_line_2 = StringProperty(required=True)
    summary_version = IntegerProperty(default=1)
    status = StringProperty(required=True, choices={"active": "Active", "retired": "Retired"})
    created_at = DateTimeProperty(default_now=True)

    appearances = RelationshipTo(
        InfoAppearanceNode,
        "APPEARS_AS",
        model=AppearanceRelationship,
        cardinality=ZeroOrMore,
    )
    narrower_concepts = RelationshipTo(
        "InfoUIDNode",
        "HAS_NARROWER_CONCEPT",
        model=ConceptHierarchyRelationship,
        cardinality=ZeroOrMore,
    )
