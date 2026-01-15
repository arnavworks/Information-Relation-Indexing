import { describe, expect, it } from "vitest";

import { buildFocusedPathGraph, buildVisibleGraph, linkEndpointId, upsertLink, upsertNode } from "@/lib/graph";
import type { GraphLink, GraphNode } from "@/lib/types";

describe("graph utilities", () => {
  it("updates a node without duplicating its identity", () => {
    const original: GraphNode = { id: "info-1", label: "Old", kind: "concept", summary: "v1" };
    const updated: GraphNode = { id: "info-1", label: "New", kind: "concept", summary: "v2" };

    expect(upsertNode([original], updated)).toEqual([updated]);
  });

  it("updates a link and resolves mutated force-graph endpoints", () => {
    const node: GraphNode = { id: "info-1", label: "Info", kind: "concept", summary: "Summary" };
    const link: GraphLink = {
      id: "root->info-1",
      source: "root",
      target: "info-1",
      relationship: "HAS_CONCEPT",
    };
    const updated = { ...link, source: node };

    expect(upsertLink([link], updated)).toEqual([updated]);
    expect(linkEndpointId(updated.source)).toBe("info-1");
  });

  it("bounds the overview and expands a focused neighborhood", () => {
    const hub: GraphNode = { id: "module", label: "Module", kind: "module", summary: "Hub" };
    const nodes: GraphNode[] = [
      hub,
      ...Array.from({ length: 40 }, (_, index) => ({
        id: `concept-${index}`,
        label: `Concept ${index}`,
        kind: "concept" as const,
        summary: "Summary",
      })),
      { id: "point", label: "Point", kind: "coordinate", summary: "Evidence" },
    ];
    const links: GraphLink[] = [
      ...nodes.slice(1, 41).map((node) => ({
        id: `module->${node.id}`,
        source: hub.id,
        target: node.id,
        relationship: "HAS_CONCEPT" as const,
      })),
      { id: "concept-39->point", source: "concept-39", target: "point", relationship: "RESOLVES_TO" },
    ];

    const overview = buildVisibleGraph({ nodes, links }, []);
    expect(overview.nodes.filter((node) => node.kind === "concept")).toHaveLength(6);
    const focused = buildVisibleGraph({ nodes, links }, ["point"]);
    expect(focused.nodes.map((node) => node.id)).toEqual(expect.arrayContaining(["point", "concept-39", "module"]));
    expect(focused.nodes).toHaveLength(3);

    const exactPath = buildFocusedPathGraph({ nodes, links }, ["concept-39", "point"]);
    expect(exactPath.nodes.map((node) => node.id)).toEqual(["concept-39", "point"]);
    expect(exactPath.links).toHaveLength(1);
  });
});
