import type { RetrievalEvent } from "@/lib/types";

export async function* parseNdjson(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<RetrievalEvent> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed) yield JSON.parse(trimmed) as RetrievalEvent;
      }
      if (done) break;
    }
    if (buffer.trim()) yield JSON.parse(buffer) as RetrievalEvent;
  } finally {
    reader.releaseLock();
  }
}

