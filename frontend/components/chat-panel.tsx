"use client";

import { ChevronRight, Database, LoaderCircle, Send, Sigma, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { FormEvent, useMemo, useRef, useState } from "react";

import { retrieve } from "@/lib/api";
import {
  APPEARANCE_NODE_ID,
  COORDINATES_NODE_ID,
  DRI_INDEX_NODE_ID,
  FACT_SHEET_NODE_ID,
  linkEndpointId,
  OUTLINE_NODE_ID,
  ROOT_NODE_ID,
} from "@/lib/graph";
import type { Citation, EvidencePayload, FactPayload, GraphLink, GraphNode, RouteConcept } from "@/lib/types";
import { useWorkbenchStore } from "@/store/workbench";

const MAX_TRACE_RESULTS = 24;

const pipelineSteps = [
  { id: "route", label: "Route concepts" },
  { id: "evidence", label: "Resolve source coordinates" },
  { id: "synthesis", label: "Synthesize grounded answer" },
  { id: "validation", label: "Validate DRI citations" },
] as const;

type PipelineStage = (typeof pipelineSteps)[number]["id"];

function compactText(value: string, maxLength = 480): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 1)}…` : normalized;
}

function formatFact(fact: FactPayload): string {
  const value = fact.numeric_value ?? fact.date_value ?? fact.text_value ?? "—";
  const affixes = [fact.currency, fact.unit].filter(Boolean).join(" ");
  return `${fact.name}: ${affixes ? `${affixes} ` : ""}${value}`;
}

export function ChatPanel() {
  const open = useWorkbenchStore((state) => state.chatOpen);
  const setOpen = useWorkbenchStore((state) => state.setChatOpen);
  const messages = useWorkbenchStore((state) => state.messages);
  const addMessage = useWorkbenchStore((state) => state.addMessage);
  const resolveMessage = useWorkbenchStore((state) => state.resolveMessage);
  const finishMessage = useWorkbenchStore((state) => state.finishMessage);
  const focusNode = useWorkbenchStore((state) => state.focusNode);
  const beginTrace = useWorkbenchStore((state) => state.beginTrace);
  const routeConcepts = useWorkbenchStore((state) => state.routeConcepts);
  const highlightPath = useWorkbenchStore((state) => state.highlightPath);
  const completeTrace = useWorkbenchStore((state) => state.completeTrace);
  const failTrace = useWorkbenchStore((state) => state.failTrace);
  const mergeGraph = useWorkbenchStore((state) => state.mergeGraph);
  const addTelemetry = useWorkbenchStore((state) => state.addTelemetry);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"evidence" | "facts">("evidence");
  const [working, setWorking] = useState(false);
  const [pipelineStage, setPipelineStage] = useState<PipelineStage | null>(null);
  const [activeAssistantId, setActiveAssistantId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const suggested = useMemo(
    () => ["What evidence defines ownership?", "Show the relevant numerical facts"],
    [],
  );

  const prepareEvidence = (
    evidence: EvidencePayload,
    concepts: RouteConcept[],
  ): {
    nodes: GraphNode[];
    links: GraphLink[];
    pathNodeIds: string[];
    pathLinkIds: string[];
    text: string;
    citation: Citation;
  } => {
    const nodeId = evidence.coordinate;
    const nodes: GraphNode[] = [{
      id: nodeId,
      label: evidence.coordinate,
      kind: "coordinate",
      coordinate: evidence.coordinate,
      infoUid: evidence.info_uid ?? undefined,
      sinfoUid: evidence.sinfo_uid ?? undefined,
      summary: evidence.raw_text,
      value: `SHA256 ${evidence.text_sha256.slice(0, 12)}…`,
    }];
    const links: GraphLink[] = [{
      id: `${COORDINATES_NODE_ID}->${nodeId}`,
      source: COORDINATES_NODE_ID,
      target: nodeId,
      relationship: "CONTAINS",
    }];
    const pathDescriptors = evidence.paths?.length
      ? evidence.paths
      : [{
          info_uid: evidence.info_uid ?? concepts[0]?.info_uid ?? OUTLINE_NODE_ID,
          sinfo_uid: evidence.sinfo_uid ?? evidence.point_id,
        }];
    const pathNodeIds = [ROOT_NODE_ID, OUTLINE_NODE_ID, APPEARANCE_NODE_ID, COORDINATES_NODE_ID, nodeId];
    const pathLinkIds = ["schema:root-outline", "schema:root-appearance", "schema:root-coordinates", `${COORDINATES_NODE_ID}->${nodeId}`];
    for (const descriptor of pathDescriptors) {
      const conceptId = descriptor.info_uid;
      const appearanceId = `appearance:${descriptor.sinfo_uid}`;
      const conceptAppearanceLink = `${conceptId}->${appearanceId}`;
      const appearancePointLink = `${appearanceId}->${nodeId}`;
      nodes.push({
        id: appearanceId,
        label: `sinfo · ${descriptor.sinfo_uid.slice(0, 8)}`,
        kind: "appearance",
        infoUid: conceptId,
        sinfoUid: descriptor.sinfo_uid,
        summary: `Source-specific support for ${conceptId}`,
      });
      links.push(
        { id: conceptAppearanceLink, source: conceptId, target: appearanceId, relationship: "APPEARS_AS" },
        { id: `${APPEARANCE_NODE_ID}->${appearanceId}`, source: APPEARANCE_NODE_ID, target: appearanceId, relationship: "CONTAINS" },
        { id: appearancePointLink, source: appearanceId, target: nodeId, relationship: "RESOLVES_TO" },
      );
      pathNodeIds.push(conceptId, appearanceId);
      pathLinkIds.push(
        `${OUTLINE_NODE_ID}->${conceptId}`,
        `${APPEARANCE_NODE_ID}->${appearanceId}`,
        conceptAppearanceLink,
        appearancePointLink,
      );
    }
    const driCode = evidence.coordinate.match(/^DRI\d+/)?.[0];
    const driNodeId = driCode ? `dri:${driCode}` : null;
    if (driCode && useWorkbenchStore.getState().graph.nodes.some((node) => node.id === `dri:${driCode}`)) {
      const driCoordinateLink = `${driNodeId}->${nodeId}`;
      links.push({
        id: driCoordinateLink,
        source: driNodeId as string,
        target: nodeId,
        relationship: "INDEXES",
      });
      pathNodeIds.push(DRI_INDEX_NODE_ID, driNodeId as string);
      pathLinkIds.push(
        "schema:root-dri",
        `${DRI_INDEX_NODE_ID}->${driNodeId}`,
        driCoordinateLink,
      );
    }
    return {
      nodes,
      links,
      pathNodeIds,
      pathLinkIds,
      text: `[${evidence.coordinate}]  ${compactText(evidence.raw_text)}`,
      citation: { coordinate: evidence.coordinate, nodeId },
    };
  };

  const prepareFact = (fact: FactPayload): {
    nodes: GraphNode[];
    links: GraphLink[];
    pathNodeIds: string[];
    pathLinkIds: string[];
    text: string;
    coordinate: string | null;
  } => {
    const nodeId = `fact:${fact.fact_id}`;
    const linkId = `${fact.info_uid}->${nodeId}`;
    const rendered = formatFact(fact);
    const nodes: GraphNode[] = [{
      id: nodeId,
      label: fact.name,
      kind: "fact",
      infoUid: fact.info_uid,
      summary: rendered,
      value: rendered,
    }];
    const graph = useWorkbenchStore.getState().graph;
    const sourcePoint = graph.nodes.find(
      (node) => node.pointId === fact.source_point_id,
    );
    const appearance = sourcePoint
      ? graph.nodes.find(
          (node) =>
            node.kind === "appearance" &&
            node.infoUid === fact.info_uid &&
            graph.links.some(
              (link) => linkEndpointId(link.source) === node.id && linkEndpointId(link.target) === sourcePoint.id,
            ),
        )
      : null;
    const driLink = sourcePoint
      ? graph.links.find(
          (link) =>
            link.relationship === "INDEXES" &&
            linkEndpointId(link.source).startsWith("dri:") &&
            linkEndpointId(link.target) === sourcePoint.id,
        )
      : null;
    const driNodeId = driLink ? linkEndpointId(driLink.source) : null;
    const supportLink: GraphLink | null = sourcePoint
      ? { id: `${nodeId}->${sourcePoint.id}`, source: nodeId, target: sourcePoint.id, relationship: "SUPPORTS" }
      : null;
    const links: GraphLink[] = [
      { id: linkId, source: fact.info_uid, target: nodeId, relationship: "HAS_FACT" },
      { id: `${FACT_SHEET_NODE_ID}->${nodeId}`, source: FACT_SHEET_NODE_ID, target: nodeId, relationship: "CONTAINS" },
    ];
    if (supportLink) links.push(supportLink);
    return {
      nodes,
      links,
      pathNodeIds: [
        ROOT_NODE_ID,
        OUTLINE_NODE_ID,
        fact.info_uid,
        FACT_SHEET_NODE_ID,
        nodeId,
        ...(sourcePoint ? [COORDINATES_NODE_ID, sourcePoint.id] : []),
        ...(appearance ? [APPEARANCE_NODE_ID, appearance.id] : []),
        ...(driNodeId ? [DRI_INDEX_NODE_ID, driNodeId] : []),
      ],
      pathLinkIds: [
        "schema:root-outline",
        `${OUTLINE_NODE_ID}->${fact.info_uid}`,
        "schema:root-facts",
        `${FACT_SHEET_NODE_ID}->${nodeId}`,
        linkId,
        ...(sourcePoint && supportLink
          ? ["schema:root-coordinates", `${COORDINATES_NODE_ID}->${sourcePoint.id}`, supportLink.id]
          : []),
        ...(appearance && sourcePoint
          ? [
              "schema:root-appearance",
              `${APPEARANCE_NODE_ID}->${appearance.id}`,
              `${fact.info_uid}->${appearance.id}`,
              `${appearance.id}->${sourcePoint.id}`,
            ]
          : []),
        ...(driNodeId && driLink
          ? ["schema:root-dri", `${DRI_INDEX_NODE_ID}->${driNodeId}`, driLink.id]
          : []),
      ],
      text: rendered,
      coordinate: sourcePoint?.coordinate ?? null,
    };
  };

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const text = query.trim();
    if (!text || working) return;
    setQuery("");
    setWorking(true);
    const assistantId = crypto.randomUUID();
    setActiveAssistantId(assistantId);
    setPipelineStage("route");
    addMessage({ id: crypto.randomUUID(), role: "user", content: text });
    addMessage({ id: assistantId, role: "assistant", content: "", pending: true, citations: [] });
    beginTrace();
    addTelemetry(`SEARCH  ${text.slice(0, 72)}`);
    let concepts: RouteConcept[] = [];
    const pendingNodes: GraphNode[] = [];
    const pendingLinks: GraphLink[] = [];
    const pathNodeIds = new Set<string>();
    const pathLinkIds = new Set<string>();
    const pathsByCoordinate = new Map<string, { nodeIds: string[]; linkIds: string[] }>();
    let graphCommitted = false;
    let answerReceived = false;
    const commitCandidatePath = () => {
      if (graphCommitted) return;
      graphCommitted = true;
      if (pendingNodes.length || pendingLinks.length) mergeGraph(pendingNodes, pendingLinks);
      if (pathNodeIds.size) highlightPath([...pathNodeIds], [...pathLinkIds]);
    };
    try {
      for await (const eventItem of retrieve(text, mode)) {
        if (eventItem.event === "route") {
          concepts = eventItem.data.concepts;
          routeConcepts(concepts);
          addTelemetry(`ROUTE   ${concepts.length} Info_UID candidate${concepts.length === 1 ? "" : "s"}`);
        } else if (eventItem.event === "stage") {
          setPipelineStage(eventItem.data.stage);
          addTelemetry(`AI      ${eventItem.data.message}`);
          if (eventItem.data.stage === "synthesis") commitCandidatePath();
        } else if (eventItem.event === "evidence") {
          if (pathsByCoordinate.size < MAX_TRACE_RESULTS) {
            const prepared = prepareEvidence(eventItem.data, concepts);
            pendingNodes.push(...prepared.nodes);
            pendingLinks.push(...prepared.links);
            prepared.pathNodeIds.forEach((id) => pathNodeIds.add(id));
            prepared.pathLinkIds.forEach((id) => pathLinkIds.add(id));
            pathsByCoordinate.set(eventItem.data.coordinate, {
              nodeIds: prepared.pathNodeIds,
              linkIds: prepared.pathLinkIds,
            });
          }
        } else if (eventItem.event === "fact") {
          if (pathsByCoordinate.size < MAX_TRACE_RESULTS) {
            const prepared = prepareFact(eventItem.data);
            pendingNodes.push(...prepared.nodes);
            pendingLinks.push(...prepared.links);
            prepared.pathNodeIds.forEach((id) => pathNodeIds.add(id));
            prepared.pathLinkIds.forEach((id) => pathLinkIds.add(id));
            if (prepared.coordinate) {
              pathsByCoordinate.set(prepared.coordinate, {
                nodeIds: prepared.pathNodeIds,
                linkIds: prepared.pathLinkIds,
              });
            }
          }
        } else if (eventItem.event === "answer") {
          commitCandidatePath();
          answerReceived = true;
          const answerNodeIds = new Set<string>();
          const answerLinkIds = new Set<string>();
          for (const coordinate of eventItem.data.citations) {
            const path = pathsByCoordinate.get(coordinate);
            path?.nodeIds.forEach((id) => answerNodeIds.add(id));
            path?.linkIds.forEach((id) => answerLinkIds.add(id));
          }
          if (answerNodeIds.size) highlightPath([...answerNodeIds], [...answerLinkIds]);
          resolveMessage(
            assistantId,
            eventItem.data.text,
            eventItem.data.citations.map((coordinate) => ({ coordinate, nodeId: coordinate })),
          );
          addTelemetry(
            `${eventItem.data.generated ? "GENERATED" : "FALLBACK"} ${eventItem.data.model ?? "evidence only"} / ${eventItem.data.citations.length} citations`,
          );
        } else if (eventItem.event === "done") {
          commitCandidatePath();
          if (!answerReceived) {
            resolveMessage(assistantId, "No source-grounded answer was returned.");
          }
          completeTrace();
          addTelemetry(`COMPLETE ${eventItem.data.evidence_count} evidence / ${eventItem.data.fact_count} facts`);
        }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Retrieval failed";
      resolveMessage(assistantId, `Retrieval unavailable. ${message}`);
      failTrace(message);
    } finally {
      finishMessage(assistantId);
      setWorking(false);
      setActiveAssistantId(null);
      setPipelineStage(null);
      requestAnimationFrame(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight }));
    }
  };

  return (
    <AnimatePresence>
      {open ? (
        <motion.aside
          className="chat-panel glass-panel"
          initial={{ opacity: 0, x: 36 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 36 }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
        >
          <header className="chat-header">
            <div><p className="eyebrow">REASONING CHANNEL</p><h2>Evidence query</h2></div>
            <button className="mini-button" onClick={() => setOpen(false)} aria-label="Close reasoning panel"><X size={16} /></button>
          </header>

          <div className="mode-switch" role="group" aria-label="Retrieval mode">
            <button className={mode === "evidence" ? "active" : ""} onClick={() => setMode("evidence")}><Database size={13} /> Evidence</button>
            <button className={mode === "facts" ? "active" : ""} onClick={() => setMode("facts")}><Sigma size={13} /> Fact sheet</button>
          </div>

          <div className="message-list" ref={scrollRef}>
            {messages.map((message) => (
              <article key={message.id} className={`message message-${message.role}`}>
                <span>{message.role === "assistant" ? "RELATION INDEX" : message.role.toUpperCase()}</span>
                {message.pending && message.id === activeAssistantId ? (
                  <div className="answer-pipeline">
                    <div><LoaderCircle className="spin" size={13} /><strong>Grounded answer pipeline</strong></div>
                    {pipelineSteps.map((step, index) => {
                      const activeIndex = pipelineSteps.findIndex((item) => item.id === pipelineStage);
                      const status = index < activeIndex ? "complete" : index === activeIndex ? "active" : "pending";
                      return <span key={step.id} className={status}><i />{step.label}</span>;
                    })}
                  </div>
                ) : null}
                <p>{message.content || (message.pending ? "Resolving graph path" : "")}</p>
                {message.citations?.length ? (
                  <div className="citation-list">
                    {message.citations.map((citation) => (
                      <button key={citation.coordinate} onClick={() => focusNode(citation.nodeId)}>
                        [{citation.coordinate}] <ChevronRight size={11} />
                      </button>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
          </div>

          {!messages.some((message) => message.role === "user") ? (
            <div className="suggested-prompts">
              {suggested.map((prompt) => <button key={prompt} onClick={() => setQuery(prompt)}>{prompt}</button>)}
            </div>
          ) : null}

          <form className="query-form" onSubmit={submit}>
            <textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void submit();
                }
              }}
              placeholder="Query the active evidence graph…"
              rows={3}
            />
            <button type="submit" disabled={!query.trim() || working} aria-label="Send query"><Send size={16} /></button>
          </form>
          <footer>Responses are limited to source-resolved evidence.</footer>
        </motion.aside>
      ) : null}
    </AnimatePresence>
  );
}
