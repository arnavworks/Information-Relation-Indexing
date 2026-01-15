import type { GraphData, GraphLink, GraphNode, TracePhase } from "@/lib/types";

export const ROOT_NODE_ID = "iri-root";
export const OUTLINE_NODE_ID = "schema:data-outline";
export const DRI_INDEX_NODE_ID = "schema:data-reference-index";
export const APPEARANCE_NODE_ID = "schema:info-appearance";
export const COORDINATES_NODE_ID = "schema:granular-coordinates";
export const FACT_SHEET_NODE_ID = "schema:fact-sheet";

export const initialGraph: GraphData = {
  nodes: [
    {
      id: ROOT_NODE_ID,
      label: "INFORMATION RELATION INDEX",
      kind: "root",
      summary: "Source-resolved relational information architecture.",
      fx: 0,
      fy: 72,
      fz: 0,
    },
    {
      id: OUTLINE_NODE_ID,
      label: "DATA OUTLINE",
      kind: "module",
      summary: "Deduplicated concepts · Unique Information Identifiers · two-line summaries",
      fx: -80,
      fy: 38,
      fz: 0,
    },
    {
      id: DRI_INDEX_NODE_ID,
      label: "DATA REFERENCE INDEX",
      kind: "module",
      summary: "Immutable registry of every physical source used for citation",
      fx: 0,
      fy: 38,
      fz: 0,
    },
    {
      id: APPEARANCE_NODE_ID,
      label: "INFO APPEARANCE",
      kind: "module",
      summary: "sinfo_uid bridges concepts to source-specific occurrences",
      fx: -40,
      fy: 38,
      fz: 0,
    },
    {
      id: COORDINATES_NODE_ID,
      label: "GRANULAR COORDINATES",
      kind: "module",
      summary: "Exact DRI(N).page-page.point evidence leaves",
      fx: 40,
      fy: 38,
      fz: 0,
    },
    {
      id: FACT_SHEET_NODE_ID,
      label: "FACT SHEET",
      kind: "module",
      summary: "Typed numerical facts, dates, units, currencies, and replayable calculations",
      fx: 80,
      fy: 38,
      fz: 0,
    },
  ],
  links: [
    { id: "schema:root-outline", source: ROOT_NODE_ID, target: OUTLINE_NODE_ID, relationship: "CONTAINS" },
    { id: "schema:root-dri", source: ROOT_NODE_ID, target: DRI_INDEX_NODE_ID, relationship: "CONTAINS" },
    { id: "schema:root-appearance", source: ROOT_NODE_ID, target: APPEARANCE_NODE_ID, relationship: "CONTAINS" },
    { id: "schema:root-coordinates", source: ROOT_NODE_ID, target: COORDINATES_NODE_ID, relationship: "CONTAINS" },
    { id: "schema:root-facts", source: ROOT_NODE_ID, target: FACT_SHEET_NODE_ID, relationship: "CONTAINS" },
  ],
};

export const nodePalette: Record<GraphNode["kind"], string> = {
  root: "#0f172a",
  module: "#475569",
  dri: "#2563eb",
  concept: "#0284c7",
  appearance: "#ea580c",
  coordinate: "#059669",
  fact: "#7c3aed",
};

export const tracePalette: Record<TracePhase, string> = {
  idle: "#64748b",
  search: "#d97706",
  route: "#ea580c",
  retrieve: "#059669",
  complete: "#0284c7",
  error: "#e11d48",
};

const overviewLimits: Partial<Record<GraphNode["kind"], number>> = {
  dri: 6,
  concept: 6,
  appearance: 4,
  coordinate: 4,
  fact: 4,
};

export function buildFocusedPathGraph(graph: GraphData, pathNodeIds: string[]): GraphData {
  const visibleIds = new Set(pathNodeIds);
  return {
    nodes: graph.nodes.filter((node) => visibleIds.has(node.id)),
    links: graph.links.filter((link) => {
      const source = linkEndpointId(link.source);
      const target = linkEndpointId(link.target);
      return visibleIds.has(source) && visibleIds.has(target);
    }),
  };
}

/**
 * Keep the browser graph readable and bounded. The complete graph remains in
 * the store; the renderer receives an overview or a small focus neighborhood.
 */
export function buildVisibleGraph(graph: GraphData, focusNodeIds: string[]): GraphData {
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
  const visibleIds = new Set(
    graph.nodes.filter((node) => node.kind === "root" || node.kind === "module").map((node) => node.id),
  );
  const validFocusIds = focusNodeIds.filter((id) => nodeById.has(id));

  if (validFocusIds.length) {
    const adjacency = new Map<string, Set<string>>();
    for (const link of graph.links) {
      const source = linkEndpointId(link.source);
      const target = linkEndpointId(link.target);
      if (!source || !target) continue;
      if (!adjacency.has(source)) adjacency.set(source, new Set());
      if (!adjacency.has(target)) adjacency.set(target, new Set());
      adjacency.get(source)?.add(target);
      adjacency.get(target)?.add(source);
    }
    let frontier = new Set(validFocusIds);
    validFocusIds.forEach((id) => visibleIds.add(id));
    for (let depth = 0; depth < 3 && visibleIds.size < 90; depth += 1) {
      const next = new Set<string>();
      for (const nodeId of frontier) {
        const node = nodeById.get(nodeId);
        if (!node || node.kind === "root" || node.kind === "module") continue;
        for (const neighborId of adjacency.get(nodeId) ?? []) {
          if (visibleIds.size >= 90) break;
          if (!visibleIds.has(neighborId)) next.add(neighborId);
          visibleIds.add(neighborId);
        }
      }
      frontier = next;
    }
  } else {
    const used = new Map<GraphNode["kind"], number>();
    for (const node of graph.nodes) {
      const limit = overviewLimits[node.kind];
      if (!limit) continue;
      const count = used.get(node.kind) ?? 0;
      if (count >= limit) continue;
      visibleIds.add(node.id);
      used.set(node.kind, count + 1);
    }
  }

  const finalNodes = graph.nodes.filter((node) => visibleIds.has(node.id));
  const finalNodeIds = new Set(finalNodes.map((n) => n.id));

  return {
    nodes: finalNodes,
    links: graph.links.filter((link) => {
      const source = linkEndpointId(link.source);
      const target = linkEndpointId(link.target);
      return Boolean(source) && Boolean(target) && finalNodeIds.has(source) && finalNodeIds.has(target);
    }),
  };
}

export function linkEndpointId(endpoint: GraphLink["source"] | null | undefined): string {
  if (!endpoint) return "";
  if (typeof endpoint === "string") return endpoint;
  if (typeof endpoint === "object" && "id" in endpoint && typeof endpoint.id === "string") {
    return endpoint.id;
  }
  return "";
}

export function upsertNode(nodes: GraphNode[], incoming: GraphNode): GraphNode[] {
  const index = nodes.findIndex((node) => node.id === incoming.id);
  if (index < 0) return [...nodes, incoming];
  const next = [...nodes];
  next[index] = { ...nodes[index], ...incoming };
  return next;
}

export function placeRelationalNode(node: GraphNode, nodes: GraphNode[]): GraphNode {
  if (node.fx !== undefined || node.kind === "root" || node.kind === "module") return node;
  const index = nodes.filter((candidate) => candidate.kind === node.kind).length;
  const column = index % 4;
  const row = Math.floor(index / 4);
  const positions: Record<Exclude<GraphNode["kind"], "root" | "module">, [number, number, number]> = {
    dri: [10 + column * 24, 12 - row * 12, 0],
    concept: [-92 + column * 24, 12 - row * 12, 0],
    appearance: [-48 + column * 24, -25 - row * 12, 0],
    coordinate: [8 + column * 27, -48 - row * 12, 0],
    fact: [-92 + column * 23, -48 - row * 11, 0],
  };
  const [fx, fy, fz] = positions[node.kind];
  return { ...node, fx, fy, fz };
}

export function upsertLink(links: GraphLink[], incoming: GraphLink): GraphLink[] {
  const index = links.findIndex((link) => link.id === incoming.id);
  if (index < 0) return [...links, incoming];
  const next = [...links];
  next[index] = incoming;
  return next;
}
