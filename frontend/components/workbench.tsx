"use client";

import { useEffect } from "react";

import { ChatPanel } from "@/components/chat-panel";
import { GraphCanvas } from "@/components/graph-canvas";
import { IngestionConsole } from "@/components/ingestion-console";
import { NodeInspector } from "@/components/node-inspector";
import { useTelemetrySocket } from "@/hooks/use-telemetry-socket";
import { backendReady, getGraphSnapshot } from "@/lib/api";
import {
  APPEARANCE_NODE_ID,
  COORDINATES_NODE_ID,
  DRI_INDEX_NODE_ID,
  FACT_SHEET_NODE_ID,
  initialGraph,
  OUTLINE_NODE_ID,
  placeRelationalNode,
  upsertLink,
  upsertNode,
} from "@/lib/graph";
import type { GraphLink, GraphNode } from "@/lib/types";
import { useWorkbenchStore } from "@/store/workbench";

export function Workbench() {
  const setBackendOnline = useWorkbenchStore((state) => state.setBackendOnline);
  const replaceGraph = useWorkbenchStore((state) => state.replaceGraph);
  const addTelemetry = useWorkbenchStore((state) => state.addTelemetry);
  useTelemetrySocket();

  useEffect(() => {
    let mounted = true;
    const check = async () => {
      const ready = await backendReady();
      if (mounted) setBackendOnline(ready);
    };
    const hydrate = async () => {
      try {
        const snapshot = await getGraphSnapshot();
        let nodes = initialGraph.nodes.map((node) => ({ ...node }));
        let links = initialGraph.links.map((link) => ({ ...link }));
        const addNode = (node: GraphNode) => {
          nodes = upsertNode(nodes, placeRelationalNode(node, nodes));
        };
        const addLink = (link: GraphLink) => {
          links = upsertLink(links, link);
        };
        const pointAppearances = new Map<string, string[]>();
        const pointCoordinates = new Map<string, string>();
        const driCodes = new Map<number, string>();
        for (const reference of snapshot.data_references) {
          driCodes.set(reference.dri_id, reference.dri_code);
          const nodeId = `dri:${reference.dri_code}`;
          addNode({
            id: nodeId,
            label: `${reference.dri_code} · ${reference.source_name}`,
            kind: "dri",
            coordinate: reference.dri_code,
            summary: `${reference.source_type.toUpperCase()} physical source registered for citation`,
          });
          addLink({
            id: `${DRI_INDEX_NODE_ID}->${nodeId}`,
            source: DRI_INDEX_NODE_ID,
            target: nodeId,
            relationship: "INDEXES",
          });
        }
        for (const concept of snapshot.concepts) {
          addNode({
            id: concept.info_uid,
            label: `INFO · ${concept.name}`,
            kind: "concept",
            infoUid: concept.info_uid,
            summary: `${concept.summary_line_1}\n${concept.summary_line_2}`,
          });
          addLink({
            id: `${OUTLINE_NODE_ID}->${concept.info_uid}`,
            source: OUTLINE_NODE_ID,
            target: concept.info_uid,
            relationship: "HAS_CONCEPT",
          });
          for (const appearance of concept.appearances) {
            const appearanceId = `appearance:${appearance.sinfo_uid}`;
            addNode({
              id: appearanceId,
              label: `sinfo · ${appearance.sinfo_uid.slice(0, 8)}`,
              kind: "appearance",
              infoUid: concept.info_uid,
              sinfoUid: appearance.sinfo_uid,
              summary: `${appearance.summary_line_1}\n${appearance.summary_line_2}`,
            });
            addLink({
              id: `${concept.info_uid}->${appearanceId}`,
              source: concept.info_uid,
              target: appearanceId,
              relationship: "APPEARS_AS",
            });
            addLink({
              id: `${APPEARANCE_NODE_ID}->${appearanceId}`,
              source: APPEARANCE_NODE_ID,
              target: appearanceId,
              relationship: "CONTAINS",
            });
            for (const pointId of appearance.point_ids) {
              const appearanceIds = pointAppearances.get(pointId) ?? [];
              pointAppearances.set(pointId, [...appearanceIds, appearanceId]);
            }
          }
        }
        for (const point of snapshot.points) {
          pointCoordinates.set(point.point_id, point.coordinate);
          addNode({
            id: point.coordinate,
            label: point.coordinate,
            kind: "coordinate",
            coordinate: point.coordinate,
            pointId: point.point_id,
            summary: point.raw_text,
          });
          addLink({
            id: `${COORDINATES_NODE_ID}->${point.coordinate}`,
            source: COORDINATES_NODE_ID,
            target: point.coordinate,
            relationship: "CONTAINS",
          });
          const driCode = driCodes.get(point.dri_id);
          const driSource = driCode ? `dri:${driCode}` : `dri:DRI${point.dri_id}`;
          addLink({
            id: `${driSource}->${point.coordinate}`,
            source: driSource,
            target: point.coordinate,
            relationship: "INDEXES",
          });
          for (const appearanceId of pointAppearances.get(point.point_id) ?? []) {
            addLink({
              id: `${appearanceId}->${point.coordinate}`,
              source: appearanceId,
              target: point.coordinate,
              relationship: "RESOLVES_TO",
            });
          }
        }
        for (const fact of snapshot.facts) {
          const nodeId = `fact:${fact.fact_id}`;
          const rendered = [fact.currency, fact.value, fact.unit].filter(Boolean).join(" ");
          addNode({
            id: nodeId,
            label: fact.name,
            kind: "fact",
            infoUid: fact.info_uid,
            summary: rendered,
            value: rendered,
          });
          addLink({
            id: `${FACT_SHEET_NODE_ID}->${nodeId}`,
            source: FACT_SHEET_NODE_ID,
            target: nodeId,
            relationship: "CONTAINS",
          });
          addLink({
            id: `${fact.info_uid}->${nodeId}`,
            source: fact.info_uid,
            target: nodeId,
            relationship: "HAS_FACT",
          });
          const sourceCoordinate = pointCoordinates.get(fact.source_point_id);
          if (sourceCoordinate) {
            addLink({
              id: `${nodeId}->${sourceCoordinate}`,
              source: nodeId,
              target: sourceCoordinate,
              relationship: "SUPPORTS",
            });
          }
        }
        replaceGraph({ nodes, links });
        addTelemetry(
          `GRAPH   ${snapshot.data_references.length} DRI / ${snapshot.concepts.length} Info_UID / ${snapshot.points.length} points`,
        );
      } catch (error) {
        addTelemetry(`WARN    graph snapshot unavailable: ${error instanceof Error ? error.message : "unknown error"}`);
      }
    };
    void check();
    void hydrate();
    window.addEventListener("dri:graph-refresh", hydrate);
    const interval = setInterval(check, 15_000);
    return () => {
      mounted = false;
      clearInterval(interval);
      window.removeEventListener("dri:graph-refresh", hydrate);
    };
  }, [addTelemetry, replaceGraph, setBackendOnline]);

  return (
    <div className="workbench-shell">
      <GraphCanvas />
      <IngestionConsole />
      <NodeInspector />
      <ChatPanel />
    </div>
  );
}
