"""Typed gateway that keeps neomodel details out of retrieval orchestration."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from neomodel.config import get_config
from neomodel.sync_.database import db

from iri.core.config import Settings
from iri.graph.models import InfoAppearanceNode, InfoUIDNode


@dataclass(frozen=True, slots=True)
class AppearancePointer:
    sinfo_uid: str
    dri_id: int
    point_ids: tuple[UUID, ...]
    coordinates: tuple[str, ...]
    summary_line_1: str
    summary_line_2: str


@dataclass(frozen=True, slots=True)
class ConceptPointer:
    info_uid: UUID
    name: str
    summary_line_1: str
    summary_line_2: str
    appearances: tuple[AppearancePointer, ...]


@dataclass(frozen=True, slots=True)
class AppearanceWrite:
    sinfo_uid: UUID
    dri_id: int
    point_ids: tuple[UUID, ...]
    coordinates: tuple[str, ...]
    summary_line_1: str
    summary_line_2: str


@dataclass(frozen=True, slots=True)
class ConceptWrite:
    info_uid: UUID
    name: str
    summary_line_1: str
    summary_line_2: str
    appearances: tuple[AppearanceWrite, ...]


def configure_graph(settings: Settings) -> None:
    """Configure neomodel once during application lifespan startup."""

    config = get_config()
    config.update(
        database_url=settings.neo4j_dsn,
        database_name=settings.neo4j_database,
        force_timezone=True,
    )


class Neo4jConceptGateway:
    """Read-only graph operations used by the online retrieval path."""

    def appearances_for(self, info_uid: UUID) -> tuple[AppearancePointer, ...]:
        node: Any = InfoUIDNode.nodes.get(info_uid=str(info_uid))
        pointers: list[AppearancePointer] = []
        for appearance in node.appearances.all():
            pointers.append(
                AppearancePointer(
                    sinfo_uid=str(appearance.sinfo_uid),
                    dri_id=int(appearance.dri_id),
                    point_ids=tuple(UUID(value) for value in appearance.point_ids),
                    coordinates=tuple(str(value) for value in appearance.coordinates),
                    summary_line_1=str(appearance.source_summary_line_1),
                    summary_line_2=str(appearance.source_summary_line_2),
                )
            )
        return tuple(pointers)

    def snapshot_concepts(self) -> tuple[ConceptPointer, ...]:
        concepts: list[ConceptPointer] = []
        for node in InfoUIDNode.nodes.all():
            pointers: list[AppearancePointer] = []
            for appearance in node.appearances.all():
                pointers.append(
                    AppearancePointer(
                        sinfo_uid=str(appearance.sinfo_uid),
                        dri_id=int(appearance.dri_id),
                        point_ids=tuple(UUID(value) for value in appearance.point_ids),
                        coordinates=tuple(str(value) for value in appearance.coordinates),
                        summary_line_1=str(appearance.source_summary_line_1),
                        summary_line_2=str(appearance.source_summary_line_2),
                    )
                )
            concepts.append(
                ConceptPointer(
                    info_uid=UUID(str(node.info_uid)),
                    name=str(node.name),
                    summary_line_1=str(node.summary_line_1),
                    summary_line_2=str(node.summary_line_2),
                    appearances=tuple(pointers),
                )
            )
        return tuple(concepts)

    def upsert_extraction(self, concepts: tuple[ConceptWrite, ...]) -> None:
        for concept in concepts:
            node: Any = InfoUIDNode.nodes.get_or_none(info_uid=str(concept.info_uid))
            if node is None:
                node = InfoUIDNode(
                    info_uid=str(concept.info_uid),
                    name=concept.name,
                    summary_line_1=concept.summary_line_1,
                    summary_line_2=concept.summary_line_2,
                    status="active",
                ).save()
            else:
                node.name = concept.name
                node.summary_line_1 = concept.summary_line_1
                node.summary_line_2 = concept.summary_line_2
                node.status = "active"
                node.save()

            for incoming in concept.appearances:
                appearance: Any = InfoAppearanceNode.nodes.get_or_none(
                    sinfo_uid=str(incoming.sinfo_uid)
                )
                if appearance is None:
                    appearance = InfoAppearanceNode(
                        sinfo_uid=str(incoming.sinfo_uid),
                        dri_id=incoming.dri_id,
                        point_ids=[str(value) for value in incoming.point_ids],
                        coordinates=list(incoming.coordinates),
                        source_summary_line_1=incoming.summary_line_1,
                        source_summary_line_2=incoming.summary_line_2,
                    ).save()
                else:
                    appearance.point_ids = [str(value) for value in incoming.point_ids]
                    appearance.coordinates = list(incoming.coordinates)
                    appearance.source_summary_line_1 = incoming.summary_line_1
                    appearance.source_summary_line_2 = incoming.summary_line_2
                    appearance.save()
                if not node.appearances.is_connected(appearance):
                    node.appearances.connect(
                        appearance,
                        {"sinfo_uid": str(incoming.sinfo_uid), "extraction_version": "1"},
                    )

    def ping(self) -> bool:
        rows, _ = db.cypher_query("RETURN 1 AS ok")
        return bool(rows and rows[0][0] == 1)
