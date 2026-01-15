# Extraction-agent contract

Parallel extraction workers exchange one frozen, versioned `ExtractionBundle`
from `iri.domain.extraction`. The bundle uses local point keys so agents
can work independently of database-generated UUIDs.

The persistence worker performs this sequence in one PostgreSQL transaction:

1. Validate all local references and typed facts.
2. Hash and insert granular points; resolve local keys to point UUIDs.
3. Deduplicate or create `Info_UID` concepts according to review policy.
4. Insert non-routable concept search projections and typed facts.
5. Insert concept, appearance, and hierarchy events into the graph outbox.
6. Mark the ingestion job complete only after validation succeeds.

Extraction agents must not write PostgreSQL or Neo4j directly. They must retain
verbatim point text, preserve page boundaries, produce exactly two concept-summary
lines, and attach every appearance and fact to a point local key. Invalid or
dangling references reject the whole bundle rather than silently losing citation
lineage.

