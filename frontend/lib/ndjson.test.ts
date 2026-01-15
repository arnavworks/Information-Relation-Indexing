import { describe, expect, it } from "vitest";

import { parseNdjson } from "@/lib/ndjson";

describe("parseNdjson", () => {
  it("reassembles events split across network chunks", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode('{"event":"route","data":{"concepts":[]}}\n{"event":"do'));
        controller.enqueue(encoder.encode('ne","data":{"fact_count":0,"evidence_count":0}}\n'));
        controller.close();
      },
    });

    const events = [];
    for await (const event of parseNdjson(stream)) events.push(event);

    expect(events.map((event) => event.event)).toEqual(["route", "done"]);
  });
});

