import { beforeEach, describe, expect, it } from "vitest";

import { initialGraph, OUTLINE_NODE_ID, ROOT_NODE_ID } from "@/lib/graph";
import { useWorkbenchStore } from "@/store/workbench";

describe("workbench trace state", () => {
  beforeEach(() => {
    useWorkbenchStore.setState({
      graph: initialGraph,
      phase: "idle",
      activeNodeIds: [],
      activeLinkIds: [],
      focusNodeId: null,
      focusNonce: 0,
    });
  });

  it("sequences search and route illumination", () => {
    const store = useWorkbenchStore.getState();
    store.beginTrace();
    expect(useWorkbenchStore.getState()).toMatchObject({
      phase: "search",
      activeNodeIds: [ROOT_NODE_ID],
    });

    useWorkbenchStore.getState().routeConcepts([
      {
        info_uid: "info-1",
        summary_line_1: "Ownership is defined.",
        summary_line_2: "The policy applies to employee work.",
        cosine_distance: 0.08,
        summary_version: 1,
      },
    ]);

    const routed = useWorkbenchStore.getState();
    expect(routed.phase).toBe("route");
    expect(routed.activeNodeIds).toEqual([ROOT_NODE_ID, OUTLINE_NODE_ID, "info-1"]);
    expect(routed.graph.links).toContainEqual(
      expect.objectContaining({ source: OUTLINE_NODE_ID, target: "info-1" }),
    );

    useWorkbenchStore.getState().highlightPath(
      [ROOT_NODE_ID, OUTLINE_NODE_ID, "info-1", "appearance-1", "point-1"],
      ["schema:root-outline", "outline->info-1", "info-1->appearance-1", "appearance-1->point-1"],
    );
    expect(useWorkbenchStore.getState()).toMatchObject({
      phase: "retrieve",
      activeNodeIds: [ROOT_NODE_ID, OUTLINE_NODE_ID, "info-1", "appearance-1", "point-1"],
    });
  });
});
