"use client";

import { create } from "zustand";

import {
  initialGraph,
  OUTLINE_NODE_ID,
  ROOT_NODE_ID,
  placeRelationalNode,
  upsertLink,
  upsertNode,
} from "@/lib/graph";
import type {
  ChatMessage,
  Citation,
  GraphData,
  GraphLink,
  GraphNode,
  IngestionFile,
  RouteConcept,
  TelemetryEvent,
  TracePhase,
} from "@/lib/types";

interface WorkbenchState {
  graph: GraphData;
  selectedNodeId: string | null;
  focusNodeId: string | null;
  focusNonce: number;
  phase: TracePhase;
  activeNodeIds: string[];
  activeLinkIds: string[];
  messages: ChatMessage[];
  files: IngestionFile[];
  telemetry: string[];
  chatOpen: boolean;
  backendOnline: boolean | null;
  socketOnline: boolean;
  setBackendOnline: (online: boolean) => void;
  setSocketOnline: (online: boolean) => void;
  setChatOpen: (open: boolean) => void;
  selectNode: (id: string | null) => void;
  focusNode: (id: string) => void;
  replaceGraph: (graph: GraphData) => void;
  mergeGraph: (nodes: GraphNode[], links: GraphLink[]) => void;
  addNode: (node: GraphNode) => void;
  addLink: (link: GraphLink) => void;
  beginTrace: () => void;
  routeConcepts: (concepts: RouteConcept[]) => void;
  retrieveNode: (nodeId: string, linkId?: string) => void;
  highlightPath: (nodeIds: string[], linkIds: string[]) => void;
  completeTrace: () => void;
  failTrace: (message: string) => void;
  addMessage: (message: ChatMessage) => void;
  appendMessage: (id: string, text: string) => void;
  resolveMessage: (id: string, content: string, citations?: Citation[]) => void;
  addCitation: (id: string, citation: Citation) => void;
  finishMessage: (id: string) => void;
  addFiles: (files: File[]) => void;
  removeFile: (id: string) => void;
  updateFile: (id: string, patch: Partial<IngestionFile>) => void;
  addTelemetry: (line: string) => void;
  applyTelemetry: (event: TelemetryEvent) => void;
}

const nowLabel = () => new Date().toLocaleTimeString([], { hour12: false });

export const useWorkbenchStore = create<WorkbenchState>((set, get) => ({
  graph: initialGraph,
  selectedNodeId: null,
  focusNodeId: null,
  focusNonce: 0,
  phase: "idle",
  activeNodeIds: [],
  activeLinkIds: [],
  messages: [
    {
      id: "welcome",
      role: "system",
      content: "Audit channel ready. Register evidence or query the active concept index.",
    },
  ],
  files: [],
  telemetry: ["SYSTEM  Information Relation Index initialized"],
  chatOpen: true,
  backendOnline: null,
  socketOnline: false,
  setBackendOnline: (backendOnline) => set({ backendOnline }),
  setSocketOnline: (socketOnline) => set({ socketOnline }),
  setChatOpen: (chatOpen) => set({ chatOpen }),
  selectNode: (selectedNodeId) => set({ selectedNodeId }),
  focusNode: (focusNodeId) =>
    set((state) => ({ focusNodeId, focusNonce: state.focusNonce + 1, selectedNodeId: focusNodeId })),
  replaceGraph: (graph) => set({ graph }),
  mergeGraph: (nodes, links) =>
    set((state) => {
      let nextNodes = state.graph.nodes;
      for (const node of nodes) {
        nextNodes = upsertNode(nextNodes, placeRelationalNode(node, nextNodes));
      }
      let nextLinks = state.graph.links;
      for (const link of links) nextLinks = upsertLink(nextLinks, link);
      return { graph: { nodes: nextNodes, links: nextLinks } };
    }),
  addNode: (node) =>
    set((state) => ({
      graph: {
        ...state.graph,
        nodes: upsertNode(state.graph.nodes, placeRelationalNode(node, state.graph.nodes)),
      },
    })),
  addLink: (link) =>
    set((state) => ({ graph: { ...state.graph, links: upsertLink(state.graph.links, link) } })),
  beginTrace: () =>
    set({ phase: "search", activeNodeIds: [ROOT_NODE_ID], activeLinkIds: [] }),
  routeConcepts: (concepts) => {
    set((state) => {
      let nodes = state.graph.nodes;
      let links = state.graph.links;
      for (const concept of concepts) {
        const node = placeRelationalNode({
        id: concept.info_uid,
        infoUid: concept.info_uid,
        label: `INFO · ${concept.info_uid.slice(0, 8).toUpperCase()}`,
        kind: "concept",
        summary: `${concept.summary_line_1}\n${concept.summary_line_2}`,
        value: `${(1 - concept.cosine_distance).toFixed(3)} confidence`,
        }, nodes);
        nodes = upsertNode(nodes, node);
        links = upsertLink(links, {
        id: `${OUTLINE_NODE_ID}->${concept.info_uid}`,
        source: OUTLINE_NODE_ID,
        target: concept.info_uid,
        relationship: "HAS_CONCEPT",
        });
      }
      return {
        graph: { nodes, links },
        phase: "route" as const,
        activeNodeIds: [ROOT_NODE_ID, OUTLINE_NODE_ID, ...concepts.map((concept) => concept.info_uid)],
        activeLinkIds: [
          "schema:root-outline",
          ...concepts.map((concept) => `${OUTLINE_NODE_ID}->${concept.info_uid}`),
        ],
      };
    });
  },
  retrieveNode: (nodeId, linkId) =>
    set({
      phase: "retrieve",
      activeNodeIds: [nodeId],
      activeLinkIds: linkId ? [linkId] : [],
    }),
  highlightPath: (nodeIds, linkIds) =>
    set({
      phase: "retrieve",
      activeNodeIds: [...new Set(nodeIds)],
      activeLinkIds: [...new Set(linkIds)],
    }),
  completeTrace: () => set({ phase: "complete" }),
  failTrace: (message) => {
    get().addTelemetry(`ERROR   ${message}`);
    set({ phase: "error" });
  },
  addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  appendMessage: (id, text) =>
    set((state) => ({
      messages: state.messages.map((message) =>
        message.id === id ? { ...message, content: message.content + text } : message,
      ),
    })),
  resolveMessage: (id, content, citations) =>
    set((state) => ({
      messages: state.messages.map((message) =>
        message.id === id
          ? { ...message, content, citations: citations ?? message.citations, pending: false }
          : message,
      ),
    })),
  addCitation: (id, citation) =>
    set((state) => ({
      messages: state.messages.map((message) =>
        message.id === id
          ? {
              ...message,
              citations: (message.citations ?? []).some(
                (item) => item.coordinate === citation.coordinate,
              )
                ? message.citations
                : [...(message.citations ?? []), citation],
            }
          : message,
      ),
    })),
  finishMessage: (id) =>
    set((state) => ({
      messages: state.messages.map((message) =>
        message.id === id ? { ...message, pending: false } : message,
      ),
    })),
  addFiles: (incoming) =>
    set((state) => ({
      files: [
        ...state.files,
        ...incoming
          .filter((file) => !state.files.some((item) => item.file.name === file.name))
          .map((file) => ({ id: crypto.randomUUID(), file, status: "ready" as const })),
      ],
    })),
  removeFile: (id) => set((state) => ({ files: state.files.filter((item) => item.id !== id) })),
  updateFile: (id, patch) =>
    set((state) => ({
      files: state.files.map((item) => (item.id === id ? { ...item, ...patch } : item)),
    })),
  addTelemetry: (line) =>
    set((state) => ({ telemetry: [...state.telemetry.slice(-39), `${nowLabel()}  ${line}`] })),
  applyTelemetry: (event) => {
    if (event.type === "graph.snapshot") get().replaceGraph(event.data);
    if (event.type === "graph.node") get().addNode(event.data);
    if (event.type === "graph.edge") get().addLink(event.data);
    if (event.type === "telemetry.log") get().addTelemetry(event.data.message);
    if (event.type === "answer.delta") {
      const pending = [...get().messages].reverse().find((message) => message.pending);
      if (pending) get().appendMessage(pending.id, event.data.text);
    }
    if (event.type === "trace.phase") {
      const { phase, nodeId } = event.data;
      if (phase === "search") get().beginTrace();
      else if (phase === "retrieve" && nodeId) get().retrieveNode(nodeId);
      else if (phase === "complete") get().completeTrace();
      else set({ phase, activeNodeIds: nodeId ? [nodeId] : [] });
    }
  },
}));
