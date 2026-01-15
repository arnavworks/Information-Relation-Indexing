"use client";

import type { PointerEvent as ReactPointerEvent, WheelEvent as ReactWheelEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  APPEARANCE_NODE_ID,
  buildFocusedPathGraph,
  buildVisibleGraph,
  COORDINATES_NODE_ID,
  DRI_INDEX_NODE_ID,
  FACT_SHEET_NODE_ID,
  linkEndpointId,
  nodePalette,
  OUTLINE_NODE_ID,
  ROOT_NODE_ID,
  tracePalette,
} from "@/lib/graph";
import type { GraphData, GraphLink, GraphNode } from "@/lib/types";
import { useWorkbenchStore } from "@/store/workbench";

interface Size {
  width: number;
  height: number;
}

interface ViewBox extends Size {
  x: number;
  y: number;
}

interface LayoutNode {
  node: GraphNode;
  x: number;
  y: number;
  width: number;
  height: number;
}

const CARD_WIDTH = 224;
const CARD_HEIGHT = 68;
const ROW_GAP = 94;
const DYNAMIC_START_Y = 280;

const columnX: Record<GraphNode["kind"], number> = {
  root: 600,
  module: 600,
  fact: 0,
  concept: 300,
  appearance: 600,
  coordinate: 900,
  dri: 1200,
};

const moduleX: Record<string, number> = {
  [FACT_SHEET_NODE_ID]: columnX.fact,
  [OUTLINE_NODE_ID]: columnX.concept,
  [APPEARANCE_NODE_ID]: columnX.appearance,
  [COORDINATES_NODE_ID]: columnX.coordinate,
  [DRI_INDEX_NODE_ID]: columnX.dri,
};

function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [size, setSize] = useState<Size>({ width: 1200, height: 760 });
  useEffect(() => {
    if (!ref.current) return;
    const observer = new ResizeObserver(([entry]) => {
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return { ref, ...size };
}

function truncate(value: string, length: number): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > length ? `${normalized.slice(0, length - 1)}…` : normalized;
}

function average(values: number[]): number | undefined {
  return values.length ? values.reduce((total, value) => total + value, 0) / values.length : undefined;
}

function layoutGraph(graph: GraphData): LayoutNode[] {
  const links = graph.links.map((link) => ({
    source: linkEndpointId(link.source),
    target: linkEndpointId(link.target),
  }));
  const proposedY = new Map<string, number>();
  const byKind = new Map<GraphNode["kind"], GraphNode[]>();
  for (const node of graph.nodes) {
    byKind.set(node.kind, [...(byKind.get(node.kind) ?? []), node]);
  }

  const coordinates = byKind.get("coordinate") ?? [];
  coordinates.forEach((node, index) => proposedY.set(node.id, DYNAMIC_START_Y + index * ROW_GAP));

  const assignFromTargets = (kind: GraphNode["kind"], targetKind: GraphNode["kind"]) => {
    const targets = new Set((byKind.get(targetKind) ?? []).map((node) => node.id));
    for (const node of byKind.get(kind) ?? []) {
      const ys = links
        .filter((link) => link.source === node.id && targets.has(link.target))
        .map((link) => proposedY.get(link.target))
        .filter((value): value is number => value !== undefined);
      const y = average(ys);
      if (y !== undefined) proposedY.set(node.id, y);
    }
  };

  assignFromTargets("appearance", "coordinate");
  assignFromTargets("dri", "coordinate");
  assignFromTargets("fact", "coordinate");

  const appearancesAndFacts = new Set([
    ...(byKind.get("appearance") ?? []).map((node) => node.id),
    ...(byKind.get("fact") ?? []).map((node) => node.id),
  ]);
  for (const node of byKind.get("concept") ?? []) {
    const ys = links
      .filter((link) => link.source === node.id && appearancesAndFacts.has(link.target))
      .map((link) => proposedY.get(link.target))
      .filter((value): value is number => value !== undefined);
    const y = average(ys);
    if (y !== undefined) proposedY.set(node.id, y);
  }

  for (const kind of ["fact", "concept", "appearance", "coordinate", "dri"] as const) {
    const nodes = byKind.get(kind) ?? [];
    let nextFallback = DYNAMIC_START_Y;
    for (const node of nodes) {
      if (!proposedY.has(node.id)) {
        proposedY.set(node.id, nextFallback);
        nextFallback += ROW_GAP;
      }
    }
    const ordered = [...nodes].sort(
      (left, right) => (proposedY.get(left.id) ?? 0) - (proposedY.get(right.id) ?? 0),
    );
    let previous = DYNAMIC_START_Y - ROW_GAP;
    for (const node of ordered) {
      const y = Math.max(proposedY.get(node.id) ?? DYNAMIC_START_Y, previous + ROW_GAP);
      proposedY.set(node.id, y);
      previous = y;
    }
  }

  return graph.nodes.map((node) => {
    if (node.id === ROOT_NODE_ID) {
      return { node, x: columnX.root, y: 30, width: 250, height: 72 };
    }
    if (node.kind === "module") {
      return { node, x: moduleX[node.id] ?? columnX.module, y: 150, width: 238, height: 72 };
    }
    return {
      node,
      x: columnX[node.kind],
      y: proposedY.get(node.id) ?? DYNAMIC_START_Y,
      width: CARD_WIDTH,
      height: CARD_HEIGHT,
    };
  });
}

function graphBounds(nodes: LayoutNode[]): ViewBox {
  if (!nodes.length) return { x: -150, y: -80, width: 1500, height: 900 };
  const left = Math.min(...nodes.map((node) => node.x - node.width / 2));
  const right = Math.max(...nodes.map((node) => node.x + node.width / 2));
  const top = Math.min(...nodes.map((node) => node.y - node.height / 2));
  const bottom = Math.max(...nodes.map((node) => node.y + node.height / 2));
  return { x: left - 70, y: top - 70, width: right - left + 140, height: bottom - top + 140 };
}

function fitBounds(bounds: ViewBox, viewport: Size): ViewBox {
  const viewportRatio = viewport.width / Math.max(viewport.height, 1);
  const contentRatio = bounds.width / Math.max(bounds.height, 1);
  if (contentRatio > viewportRatio) {
    const height = bounds.width / viewportRatio;
    return { x: bounds.x, y: bounds.y - (height - bounds.height) / 2, width: bounds.width, height };
  }
  const width = bounds.height * viewportRatio;
  return { x: bounds.x - (width - bounds.width) / 2, y: bounds.y, width, height: bounds.height };
}

function cardBoundary(from: LayoutNode, toward: LayoutNode): { x: number; y: number } {
  const dx = toward.x - from.x;
  const dy = toward.y - from.y;
  if (!dx && !dy) return { x: from.x, y: from.y };
  const scale = 1 / Math.max(Math.abs(dx) / (from.width / 2), Math.abs(dy) / (from.height / 2));
  return { x: from.x + dx * scale, y: from.y + dy * scale };
}

export function GraphCanvas() {
  const graph = useWorkbenchStore((state) => state.graph);
  const phase = useWorkbenchStore((state) => state.phase);
  const activeNodeIds = useWorkbenchStore((state) => state.activeNodeIds);
  const activeLinkIds = useWorkbenchStore((state) => state.activeLinkIds);
  const focusNodeId = useWorkbenchStore((state) => state.focusNodeId);
  const focusNonce = useWorkbenchStore((state) => state.focusNonce);
  const selectedNodeId = useWorkbenchStore((state) => state.selectedNodeId);
  const chatOpen = useWorkbenchStore((state) => state.chatOpen);
  const setChatOpen = useWorkbenchStore((state) => state.setChatOpen);
  const selectNode = useWorkbenchStore((state) => state.selectNode);
  const { ref: containerRef, width, height } = useElementSize<HTMLDivElement>();
  const svgRef = useRef<SVGSVGElement>(null);
  const dragRef = useRef<{ x: number; y: number; view: ViewBox } | null>(null);
  const [overviewOnly, setOverviewOnly] = useState(false);
  const [viewBox, setViewBox] = useState<ViewBox | null>(null);

  const activeNodes = useMemo(() => new Set(activeNodeIds), [activeNodeIds]);
  const activeLinks = useMemo(() => new Set(activeLinkIds), [activeLinkIds]);
  const focusIds = useMemo(
    () => overviewOnly ? [] : [...activeNodeIds, ...(selectedNodeId ? [selectedNodeId] : [])],
    [activeNodeIds, overviewOnly, selectedNodeId],
  );
  const visibleGraph = useMemo(() => {
    if (!overviewOnly && activeNodeIds.length > 1) return buildFocusedPathGraph(graph, focusIds);
    return buildVisibleGraph(graph, focusIds);
  }, [activeNodeIds.length, focusIds, graph, overviewOnly]);
  const layout = useMemo(() => layoutGraph(visibleGraph), [visibleGraph]);
  const layoutById = useMemo(() => new Map(layout.map((node) => [node.node.id, node])), [layout]);
  const bounds = useMemo(() => graphBounds(layout), [layout]);
  const fittedView = useMemo(() => fitBounds(bounds, { width, height }), [bounds, height, width]);
  const currentView = viewBox ?? fittedView;
  const activeColor = tracePalette[phase];

  const traceSteps = useMemo(() => {
    const activeKinds = new Set(
      graph.nodes.filter((node) => activeNodes.has(node.id)).map((node) => node.kind),
    );
    return [
      { label: "QUERY", active: phase !== "idle" && phase !== "error" },
      { label: "OUTLINE", active: activeNodes.has(OUTLINE_NODE_ID) },
      { label: "INFO_UID", active: activeKinds.has("concept") },
      { label: "sinfo_UID", active: activeKinds.has("appearance") },
      { label: "DRI", active: activeKinds.has("dri") },
      { label: "COORDINATE", active: activeKinds.has("coordinate") },
      { label: "FACT", active: activeKinds.has("fact") },
    ];
  }, [activeNodes, graph.nodes, phase]);

  const fitView = useCallback(() => setViewBox(fittedView), [fittedView]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => setViewBox(fittedView));
    return () => window.cancelAnimationFrame(frame);
  }, [fittedView]);

  useEffect(() => {
    const node = focusNodeId ? layoutById.get(focusNodeId) : null;
    if (!node) return;
    const frame = window.requestAnimationFrame(() => {
      const zoomWidth = 620;
      const zoomHeight = zoomWidth / (width / Math.max(height, 1));
      setViewBox({ x: node.x - zoomWidth / 2, y: node.y - zoomHeight / 2, width: zoomWidth, height: zoomHeight });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [focusNodeId, focusNonce, height, layoutById, width]);

  const zoom = (event: ReactWheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const factor = event.deltaY > 0 ? 1.12 : 0.88;
    const pointerX = currentView.x + ((event.clientX - rect.left) / rect.width) * currentView.width;
    const pointerY = currentView.y + ((event.clientY - rect.top) / rect.height) * currentView.height;
    const nextWidth = currentView.width * factor;
    const nextHeight = currentView.height * factor;
    const ratioX = (pointerX - currentView.x) / currentView.width;
    const ratioY = (pointerY - currentView.y) / currentView.height;
    setViewBox({
      x: pointerX - ratioX * nextWidth,
      y: pointerY - ratioY * nextHeight,
      width: nextWidth,
      height: nextHeight,
    });
  };

  const startPan = (event: ReactPointerEvent<SVGSVGElement>) => {
    if ((event.target as Element).closest(".graph-node-card")) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { x: event.clientX, y: event.clientY, view: currentView };
  };

  const pan = (event: ReactPointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    setViewBox({
      ...drag.view,
      x: drag.view.x - ((event.clientX - drag.x) / width) * drag.view.width,
      y: drag.view.y - ((event.clientY - drag.y) / height) * drag.view.height,
    });
  };

  return (
    <main
      ref={containerRef}
      className={`graph-stage ${chatOpen ? "has-chat" : ""}`}
      aria-label="Interactive 2D relational information graph"
    >
      <div className="graph-grid" />
      <svg
        ref={svgRef}
        className="graph-svg"
        viewBox={`${currentView.x} ${currentView.y} ${currentView.width} ${currentView.height}`}
        onWheel={zoom}
        onPointerDown={startPan}
        onPointerMove={pan}
        onPointerUp={() => { dragRef.current = null; }}
        onPointerCancel={() => { dragRef.current = null; }}
        role="img"
        aria-label="Source-resolved graph with edge-anchored relationships"
      >
        <defs>
          <marker id="arrow-default" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L8,4 L0,8 Z" fill="#94a3b8" />
          </marker>
          <marker id="arrow-active" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L8,4 L0,8 Z" fill={activeColor} />
          </marker>
        </defs>

        <g className="graph-links">
          {visibleGraph.links.map((link) => {
            const source = layoutById.get(linkEndpointId(link.source));
            const target = layoutById.get(linkEndpointId(link.target));
            if (!source || !target) return null;
            const start = cardBoundary(source, target);
            const end = cardBoundary(target, source);
            const active = activeLinks.has(link.id);
            const showLabel = active || visibleGraph.links.length <= 12;
            const midX = (start.x + end.x) / 2;
            const midY = (start.y + end.y) / 2;
            return (
              <g key={link.id} className={`graph-link ${active ? "active" : ""}`}>
                <title>{`${source.node.label} — ${link.relationship} → ${target.node.label}`}</title>
                <line
                  x1={start.x}
                  y1={start.y}
                  x2={end.x}
                  y2={end.y}
                  stroke={active ? activeColor : "#b8c2cf"}
                  strokeWidth={active ? 2.2 : 1.15}
                  markerEnd={`url(#arrow-${active ? "active" : "default"})`}
                />
                {showLabel ? (
                  <g className="graph-link-label" transform={`translate(${midX} ${midY})`}>
                    <rect x="-38" y="-9" width="76" height="18" rx="5" />
                    <text textAnchor="middle" dominantBaseline="central">{link.relationship}</text>
                  </g>
                ) : null}
              </g>
            );
          })}
        </g>

        <g className="graph-nodes">
          {layout.map(({ node, x, y, width: nodeWidth, height: nodeHeight }) => {
            const active = activeNodes.has(node.id);
            const selected = selectedNodeId === node.id;
            const color = active ? activeColor : nodePalette[node.kind];
            return (
              <g
                key={node.id}
                className={`graph-node-card ${active ? "active" : ""}`}
                transform={`translate(${x - nodeWidth / 2} ${y - nodeHeight / 2})`}
                onClick={(event) => { event.stopPropagation(); selectNode(node.id); }}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") selectNode(node.id);
                }}
              >
                <title>{`${node.label}\n${node.summary}`}</title>
                <rect className="node-depth" x="4" y="5" width={nodeWidth} height={nodeHeight} rx="9" />
                <rect
                  className="node-face"
                  width={nodeWidth}
                  height={nodeHeight}
                  rx="9"
                  fill={node.kind === "module" ? "#f8fafc" : "#ffffff"}
                  stroke={active || selected ? color : "#cbd5e1"}
                  strokeWidth={active || selected ? 2 : 1.2}
                />
                <rect width="5" height={nodeHeight} rx="2.5" fill={color} />
                <text className="node-kind-label" x="17" y="18" fill={color}>{node.kind.toUpperCase()}</text>
                <text className="node-title" x="17" y="39">{truncate(node.label, node.kind === "module" ? 29 : 31)}</text>
                <text className="node-detail" x="17" y="57">{truncate(node.coordinate ?? node.summary, 40)}</text>
              </g>
            );
          })}
        </g>
      </svg>

      <div className="graph-actions">
        {!chatOpen ? (
          <button type="button" onClick={() => setChatOpen(true)} style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--blue)", borderColor: "#93c5fd", background: "#eff6ff" }}>
            <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            EVIDENCE QUERY
          </button>
        ) : null}
        <button type="button" className={overviewOnly ? "active" : ""} onClick={() => setOverviewOnly(!overviewOnly)}>
          {overviewOnly ? "QUERY FOCUS" : "OVERVIEW"}
        </button>
        <button type="button" onClick={fitView}>FIT VIEW</button>
      </div>

      <div className="graph-trace" aria-label="Active provenance trace">
        <strong>PROVENANCE</strong>
        {traceSteps.map((step, index) => (
          <span key={step.label} className={step.active ? "active" : ""}>
            {index ? <i>→</i> : null}{step.label}
          </span>
        ))}
      </div>

      <div className="graph-caption">
        <span>{visibleGraph.nodes.length} / {graph.nodes.length} NODES</span>
        <span>{visibleGraph.links.length} VISIBLE EDGES</span>
        <span>{focusIds.length && !overviewOnly ? "EXACT PROVENANCE PATH" : "OVERVIEW"}</span>
      </div>
      <div className="graph-legend">
        {(["module", "dri", "concept", "appearance", "coordinate", "fact"] as const).map((kind) => (
          <span key={kind}><i style={{ background: nodePalette[kind] }} />{kind}</span>
        ))}
      </div>
    </main>
  );
}

export function isLinkAttached(link: GraphLink, nodeId: string): boolean {
  return linkEndpointId(link.source) === nodeId || linkEndpointId(link.target) === nodeId;
}
