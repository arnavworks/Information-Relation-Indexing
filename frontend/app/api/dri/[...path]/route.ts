import type { NextRequest } from "next/server";

const backendUrl = process.env.DRI_BACKEND_URL ?? "http://127.0.0.1:8000";

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  const target = new URL(path.join("/"), `${backendUrl.replace(/\/$/, "")}/`);
  target.search = request.nextUrl.search;

  const headers = new Headers();
  for (const name of ["content-type", "idempotency-key", "authorization"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
      // Required by Node fetch when forwarding a streaming request body.
      duplex: "half",
      cache: "no-store",
    } as RequestInit & { duplex: "half" });
    const responseHeaders = new Headers();
    const contentType = upstream.headers.get("content-type");
    if (contentType) responseHeaders.set("content-type", contentType);
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  } catch {
    return Response.json({ detail: "Information Relation Index backend unavailable" }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
