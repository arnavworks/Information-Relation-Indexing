export type NodeKind =
  | "root"
  | "module"
  | "dri"
  | "concept"
  | "appearance"
  | "coordinate"
  | "fact";
export type TracePhase = "idle" | "search" | "route" | "retrieve" | "complete" | "error";

export interface GraphNode {
  id: string;
  label: string;
  kind: NodeKind;
  summary: string;
  coordinate?: string;
  pointId?: string;
  infoUid?: string;
  sinfoUid?: string;
  value?: string;
  x?: number;
  y?: number;
  z?: number;
  vx?: number;
  vy?: number;
  vz?: number;
  fx?: number;
  fy?: number;
  fz?: number;
}

export interface GraphLink {
  id: string;
  source: string | GraphNode;
  target: string | GraphNode;
  relationship:
    | "CONTAINS"
    | "INDEXES"
    | "HAS_CONCEPT"
    | "APPEARS_AS"
    | "RESOLVES_TO"
    | "HAS_FACT"
    | "SUPPORTS";
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface RouteConcept {
  info_uid: string;
  summary_line_1: string;
  summary_line_2: string;
  cosine_distance: number;
  summary_version: number;
}

export interface EvidencePayload {
  coordinate: string;
  point_id: string;
  raw_text: string;
  text_sha256: string;
  info_uid: string | null;
  sinfo_uid: string | null;
  paths?: Array<{ info_uid: string; sinfo_uid: string }>;
}

export interface FactPayload {
  fact_id: string;
  info_uid: string;
  source_point_id: string;
  name: string;
  value_type: string;
  numeric_value?: string | null;
  date_value?: string | null;
  text_value?: string | null;
  unit?: string | null;
  currency?: string | null;
}

export type RetrievalEvent =
  | { event: "route"; data: { concepts: RouteConcept[] } }
  | { event: "stage"; data: { stage: "evidence" | "synthesis" | "validation"; message: string } }
  | { event: "evidence"; data: EvidencePayload }
  | { event: "fact"; data: FactPayload }
  | { event: "answer"; data: { text: string; citations: string[]; model: string | null; grounded: boolean; generated: boolean } }
  | { event: "done"; data: { fact_count: number; evidence_count: number } };

export type TelemetryEvent =
  | { type: "graph.snapshot"; data: GraphData }
  | { type: "graph.node"; data: GraphNode }
  | { type: "graph.edge"; data: GraphLink }
  | { type: "trace.phase"; data: { phase: TracePhase; nodeId?: string } }
  | { type: "telemetry.log"; data: { message: string } }
  | { type: "answer.delta"; data: { text: string } };

export interface Citation {
  coordinate: string;
  nodeId: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations?: Citation[];
  pending?: boolean;
}

export interface IngestionFile {
  id: string;
  file: File;
  status: "ready" | "hashing" | "queued" | "processing" | "complete" | "failed";
  driCode?: string;
  jobId?: string;
  error?: string;
}

export interface GraphSnapshot {
  data_references: Array<{
    dri_id: number;
    dri_code: string;
    source_name: string;
    source_type: string;
  }>;
  concepts: Array<{
    info_uid: string;
    name: string;
    summary_line_1: string;
    summary_line_2: string;
    appearances: Array<{
      sinfo_uid: string;
      dri_id: number;
      point_ids: string[];
      coordinates: string[];
      summary_line_1: string;
      summary_line_2: string;
    }>;
  }>;
  points: Array<{
    point_id: string;
    dri_id: number;
    coordinate: string;
    raw_text: string;
  }>;
  facts: Array<{
    fact_id: string;
    info_uid: string;
    source_point_id: string;
    name: string;
    value_type: string;
    value: string;
    unit: string | null;
    currency: string | null;
  }>;
}
