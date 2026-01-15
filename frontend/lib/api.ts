import { parseNdjson } from "@/lib/ndjson";
import type { GraphSnapshot, IngestionFile, RetrievalEvent } from "@/lib/types";

const API_BASE = "/api/dri";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export async function registerFile(item: IngestionFile): Promise<{
  job_id: string;
  dri_id: number;
  dri_code: string;
  status: string;
}> {
  const file = item.file;
  const body = new FormData();
  body.set("file", file, file.name);
  const response = await fetch(`${API_BASE}/v1/ingestions/upload`, {
    method: "POST",
    headers: {
      "Idempotency-Key": item.id,
    },
    body,
  });
  if (!response.ok) throw new ApiError(await response.text(), response.status);
  return response.json();
}

export async function getIngestion(jobId: string): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE}/v1/ingestions/${jobId}`, { cache: "no-store" });
  if (!response.ok) throw new ApiError(await response.text(), response.status);
  return response.json();
}

export async function* retrieve(
  query: string,
  mode: "evidence" | "facts" = "evidence",
): AsyncGenerator<RetrievalEvent> {
  const response = await fetch(`${API_BASE}/v1/retrieval/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, mode, concept_limit: 5 }),
  });
  if (!response.ok) throw new ApiError(await response.text(), response.status);
  if (!response.body) throw new ApiError("Retrieval stream did not include a body", 502);
  yield* parseNdjson(response.body);
}

export async function backendReady(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/health/ready`, { cache: "no-store" });
    return response.ok;
  } catch {
    return false;
  }
}

export async function getGraphSnapshot(): Promise<GraphSnapshot> {
  const response = await fetch(`${API_BASE}/v1/graph/snapshot`, { cache: "no-store" });
  if (!response.ok) throw new ApiError(await response.text(), response.status);
  return response.json();
}
