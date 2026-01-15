"use client";

import { FileJson, FileText, LoaderCircle, Network, Plus, Trash2, UploadCloud } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRef, useState } from "react";

import { getIngestion, registerFile } from "@/lib/api";
import { DRI_INDEX_NODE_ID } from "@/lib/graph";
import type { IngestionFile } from "@/lib/types";
import { useWorkbenchStore } from "@/store/workbench";

const sleep = (milliseconds: number) => new Promise((resolve) => setTimeout(resolve, milliseconds));

export function IngestionConsole() {
  const files = useWorkbenchStore((state) => state.files);
  const addFiles = useWorkbenchStore((state) => state.addFiles);
  const removeFile = useWorkbenchStore((state) => state.removeFile);
  const updateFile = useWorkbenchStore((state) => state.updateFile);
  const addTelemetry = useWorkbenchStore((state) => state.addTelemetry);
  const addNode = useWorkbenchStore((state) => state.addNode);
  const addLink = useWorkbenchStore((state) => state.addLink);
  const telemetry = useWorkbenchStore((state) => state.telemetry);
  const [dragging, setDragging] = useState(false);
  const [working, setWorking] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const poll = async (item: IngestionFile, jobId: string) => {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      await sleep(2_000);
      const result = await getIngestion(jobId);
      if (["processing", "complete", "failed"].includes(result.status)) {
        updateFile(item.id, { status: result.status as IngestionFile["status"] });
        addTelemetry(`AGENT   ${item.file.name} / ${result.status.toUpperCase()}`);
      }
      if (result.status === "complete") {
        window.dispatchEvent(new Event("dri:graph-refresh"));
        return;
      }
      if (result.status === "failed") return;
    }
  };

  const createGraph = async () => {
    const pending = files.filter((item) => item.status === "ready" || item.status === "failed");
    if (!pending.length || working) return;
    setWorking(true);
    addTelemetry(`INGEST  preparing ${pending.length} source${pending.length === 1 ? "" : "s"}`);
    await Promise.allSettled(
      pending.map(async (item) => {
        try {
          updateFile(item.id, { status: "hashing", error: undefined });
          addTelemetry(`HASH    ${item.file.name}`);
          const result = await registerFile(item);
          updateFile(item.id, { status: "queued", jobId: result.job_id, driCode: result.dri_code });
          addTelemetry(`DRI     ${result.dri_code} registered / extraction queued`);
          const nodeId = `dri:${result.dri_code}`;
          addNode({
            id: nodeId,
            label: result.dri_code,
            kind: "dri",
            summary: `${item.file.name} · ${item.file.type || "unstructured source"}`,
            coordinate: result.dri_code,
          });
          addLink({
            id: `${DRI_INDEX_NODE_ID}->${nodeId}`,
            source: DRI_INDEX_NODE_ID,
            target: nodeId,
            relationship: "INDEXES",
          });
          void poll(item, result.job_id);
        } catch (error) {
          const message = error instanceof Error ? error.message : "Registration failed";
          updateFile(item.id, { status: "failed", error: message });
          addTelemetry(`ERROR   ${item.file.name} / registration failed`);
        }
      }),
    );
    setWorking(false);
  };

  return (
    <section className="ingestion-console glass-panel">
      <div
        className={`drop-zone ${dragging ? "is-dragging" : ""}`}
        onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          addFiles(Array.from(event.dataTransfer.files));
        }}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => event.key === "Enter" && inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          hidden
          multiple
          type="file"
          accept=".pdf,.json,.csv,.txt,.md"
          onChange={(event) => addFiles(Array.from(event.target.files ?? []))}
        />
        <UploadCloud size={18} />
        <span>DROP SOURCES</span>
        <small>PDF · JSON · TABULAR · DOCUMENT</small>
      </div>

      <AnimatePresence initial={false}>
        {files.length ? (
          <motion.div className="file-queue" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}>
            {files.map((item) => (
              <div className="file-row" key={item.id}>
                {item.file.name.endsWith(".json") ? <FileJson size={15} /> : <FileText size={15} />}
                <span title={item.file.name}>{item.file.name}</span>
                {item.driCode ? <code>{item.driCode}</code> : null}
                <em className={`file-status status-${item.status}`}>{item.status}</em>
                <button onClick={() => removeFile(item.id)} aria-label={`Remove ${item.file.name}`}><Trash2 size={13} /></button>
              </div>
            ))}
          </motion.div>
        ) : null}
      </AnimatePresence>

      <button className="create-graph-button" onClick={createGraph} disabled={working || !files.length}>
        {working ? <LoaderCircle className="spin" size={16} /> : <Network size={16} />}
        [ CREATE INFO GRAPH ]
        {!files.length ? <Plus size={14} /> : <span>{files.length}</span>}
      </button>

      <div className="telemetry-terminal" aria-live="polite">
        <div className="terminal-head"><span>AGENT TELEMETRY</span><i /></div>
        <div className="terminal-lines">
          {telemetry.slice(-5).map((line, index) => <p key={`${line}-${index}`}>{line}</p>)}
        </div>
      </div>
    </section>
  );
}
