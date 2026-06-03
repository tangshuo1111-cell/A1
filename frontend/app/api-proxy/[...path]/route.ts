import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

function backendBaseUrl(): string {
  return (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
}

function buildTargetUrl(path: string[], request: NextRequest): string {
  const suffix = path.length ? `/${path.join("/")}` : "";
  const url = new URL(request.url);
  const query = url.search || "";
  return `${backendBaseUrl()}${suffix}${query}`;
}

function copyRequestHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (lower === "host" || lower === "content-length") {
      return;
    }
    headers.set(key, value);
  });
  return headers;
}

function copyResponseHeaders(source: Headers): Headers {
  const headers = new Headers();
  source.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (lower === "content-encoding" || lower === "transfer-encoding") {
      return;
    }
    headers.set(key, value);
  });
  return headers;
}

async function forward(request: NextRequest, path: string[]): Promise<Response> {
  const method = request.method.toUpperCase();
  const headers = copyRequestHeaders(request);
  const target = buildTargetUrl(path, request);
  const init: RequestInit & { duplex?: "half" } = {
    method,
    headers,
    body: method === "GET" || method === "HEAD" ? undefined : request.body,
    redirect: "manual",
    cache: "no-store",
  };
  if (method !== "GET" && method !== "HEAD") {
    init.duplex = "half";
  }

  try {
    const upstream = await fetch(target, init);

    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: copyResponseHeaders(upstream.headers),
    });
  } catch {
    return Response.json(
      {
        ok: false,
        error: {
          code: "UPSTREAM_PROXY_FAILED",
          message: "前端代理转发后端请求失败，请稍后重试。",
        },
      },
      { status: 502 },
    );
  }
}

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

export async function GET(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path = [] } = await context.params;
  return forward(request, path);
}

export async function POST(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path = [] } = await context.params;
  return forward(request, path);
}

export async function PUT(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path = [] } = await context.params;
  return forward(request, path);
}

export async function PATCH(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path = [] } = await context.params;
  return forward(request, path);
}

export async function DELETE(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path = [] } = await context.params;
  return forward(request, path);
}

export async function OPTIONS(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path = [] } = await context.params;
  return forward(request, path);
}
