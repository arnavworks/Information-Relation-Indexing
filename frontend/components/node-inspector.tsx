"use client";

import { Crosshair, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";

import { useWorkbenchStore } from "@/store/workbench";

export function NodeInspector() {
  const graph = useWorkbenchStore((state) => state.graph);
  const selectedNodeId = useWorkbenchStore((state) => state.selectedNodeId);
  const selectNode = useWorkbenchStore((state) => state.selectNode);
  const focusNode = useWorkbenchStore((state) => state.focusNode);
  const node = graph.nodes.find((candidate) => candidate.id === selectedNodeId);

  return (
    <AnimatePresence>
      {node ? (
        <motion.aside
          className="node-inspector glass-panel"
          initial={{ opacity: 0, y: 14, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8, scale: 0.98 }}
        >
          <div className="inspector-topline">
            <span className={`node-kind kind-${node.kind}`}>{node.kind}</span>
            <div>
              <button className="mini-button" onClick={() => focusNode(node.id)} aria-label="Focus node"><Crosshair size={14} /></button>
              <button className="mini-button" onClick={() => selectNode(null)} aria-label="Close inspector"><X size={14} /></button>
            </div>
          </div>
          <h2>{node.label}</h2>
          {node.coordinate ? <code>{node.coordinate}</code> : null}
          <p>{node.summary}</p>
          {node.value ? <div className="inspector-value">{node.value}</div> : null}
          <dl>
            {node.infoUid ? <><dt>Info_UID</dt><dd>{node.infoUid}</dd></> : null}
            {node.sinfoUid ? <><dt>sinfo_uid</dt><dd>{node.sinfoUid}</dd></> : null}
            <dt>Node ID</dt><dd>{node.id}</dd>
          </dl>
        </motion.aside>
      ) : null}
    </AnimatePresence>
  );
}

