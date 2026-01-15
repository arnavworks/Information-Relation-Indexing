# IRI Visual Interface

The frontend is a Next.js App Router application for auditable, concept-first
retrieval. It combines a force-directed Three.js graph, ingestion registration,
NDJSON evidence streaming, and synchronized trace illumination.

## Run

```bash
cp .env.local.example .env.local
npm install
npm run dev
```

The interface opens at `http://localhost:3000`. The server-side proxy forwards
`/api/dri/*` to `DRI_BACKEND_URL` (default `http://127.0.0.1:8000`), avoiding
browser CORS configuration and keeping backend topology private.

## Event contracts

The current backend streams these NDJSON events from retrieval:

- `route`: creates and illuminates candidate `Info_UID` nodes.
- `evidence`: creates the exact coordinate leaf, illuminates its edge, and only
  then reveals source text in the reasoning panel.
- `fact`: creates a typed fact leaf for numerical mode.
- `done`: completes the visual trace.

Set `NEXT_PUBLIC_DRI_WS_URL` when a backend telemetry socket is available. The
adapter accepts `graph.snapshot`, `graph.node`, `graph.edge`, `trace.phase`,
`telemetry.log`, and `answer.delta` messages and reconnects with bounded backoff.

## Ingestion behavior

Dropped PDF, JSON, CSV, Markdown, and text files are uploaded through the Next.js
proxy. The backend stores their bytes, extracts granular source points, uses Gemini
structured output to identify point-backed concepts and explicit facts, embeds the
two-line summaries, projects `Info_UID → sinfo_uid → coordinate` relationships into
Neo4j, and refreshes the graph when the durable job reaches `complete`.

Extraction runs in-process with a two-job concurrency limit for local development.
A production deployment should move the same processor behind a durable external
queue so work survives API process restarts.

Retrieval currently returns resolved evidence rather than LLM-authored prose.
The panel faithfully displays that evidence and never labels generated filler as
an answer. This is intentional: visual auditability should not outrun provenance.

## Verification

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

The latest stable Next.js currently pins PostCSS 8.4.31, which npm reports under
GHSA-qx2v-qp2m-jg93. The vulnerable stringify path is build-time and this project
does not compile user-supplied CSS. Upgrade when a patched stable Next.js release
ships; do not use npm's suggested forced downgrade.
