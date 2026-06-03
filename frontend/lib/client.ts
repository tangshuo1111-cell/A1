/**
 * 浏览器侧 HTTP 基座（基础设施层）。
 * 默认走 Next rewrites 的 /api-proxy/*；若设置 NEXT_PUBLIC_API_BASE_URL 则直连后端（需后端 CORS）。
 * 协作：lib/api.ts 调用 jsonFetch；与 next.config.ts rewrites 约定路径一致。
 */

import type { ApiErrorBody } from "./types";

export class ApiRequestError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(message: string, status: number, body?: unknown) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.body = body;
  }
}

export function resolveApiUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  const base = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (base) {
    return `${base.replace(/\/$/, "")}${p}`;
  }
  return `/api-proxy${p}`;
}

/** 与后端 `API_BEARER_TOKEN` 对齐；空则不发送 Authorization（本地开发常见）。 */
export function bearerAuthHeader(): Record<string, string> {
  const tok = process.env.NEXT_PUBLIC_API_BEARER_TOKEN?.trim();
  if (!tok) {
    return {};
  }
  return { Authorization: `Bearer ${tok}` };
}

function mergeHeaders(
  initHeaders: HeadersInit | undefined,
  defaults: Record<string, string>,
): Record<string, string> {
  const out: Record<string, string> = { ...defaults };
  if (!initHeaders) {
    return out;
  }
  if (initHeaders instanceof Headers) {
    initHeaders.forEach((v, k) => {
      out[k] = v;
    });
    return out;
  }
  if (Array.isArray(initHeaders)) {
    for (const [k, v] of initHeaders) {
      out[k] = v;
    }
    return out;
  }
  return { ...out, ...initHeaders };
}

function hasAuthorization(initHeaders: HeadersInit | undefined): boolean {
  if (!initHeaders) {
    return false;
  }
  if (initHeaders instanceof Headers) {
    return initHeaders.has("Authorization") || initHeaders.has("authorization");
  }
  if (Array.isArray(initHeaders)) {
    return initHeaders.some(([k]) => k.toLowerCase() === "authorization");
  }
  const o = initHeaders as Record<string, string>;
  return "Authorization" in o || "authorization" in o;
}

function readErrorMessage(data: unknown, fallback: string): string {
  if (
    data &&
    typeof data === "object" &&
    "error" in data &&
    (data as ApiErrorBody).error?.message
  ) {
    return String((data as ApiErrorBody).error.message);
  }
  return fallback;
}

export async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = resolveApiUrl(path);
  const defaults: Record<string, string> = { "Content-Type": "application/json" };
  if (!hasAuthorization(init?.headers)) {
    Object.assign(defaults, bearerAuthHeader());
  }
  const headers = mergeHeaders(init?.headers, defaults);
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Network error";
    throw new ApiRequestError(msg, 0);
  }

  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text) as unknown;
    } catch {
      data = text;
    }
  }

  if (!res.ok) {
    const msg = readErrorMessage(data, res.statusText || `HTTP ${res.status}`);
    throw new ApiRequestError(msg, res.status, data);
  }

  return data as T;
}

/**
 * 上传 multipart/form-data；专给 V11 R3 cookies.txt 上传用。
 * 不写 Content-Type，让 fetch 自动加 boundary。
 */
export async function multipartFetch<T>(
  path: string,
  form: FormData,
  init?: Omit<RequestInit, "body" | "method">,
): Promise<T> {
  const url = resolveApiUrl(path);
  const defaults: Record<string, string> = {};
  if (!hasAuthorization(init?.headers)) {
    Object.assign(defaults, bearerAuthHeader());
  }
  const headers = mergeHeaders(init?.headers, defaults);
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      method: "POST",
      body: form,
      headers: Object.keys(headers).length ? headers : undefined,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Network error";
    throw new ApiRequestError(msg, 0);
  }

  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text) as unknown;
    } catch {
      data = text;
    }
  }

  if (!res.ok) {
    // FastAPI 上传错误体形如 {"detail": {"code": "...", "message": "..."}}
    let msg = res.statusText || `HTTP ${res.status}`;
    if (data && typeof data === "object" && "detail" in data) {
      const d = (data as { detail: unknown }).detail;
      if (typeof d === "string") {
        msg = d;
      } else if (d && typeof d === "object" && "message" in d) {
        msg = String((d as { message: unknown }).message);
      }
    }
    throw new ApiRequestError(msg, res.status, data);
  }

  return data as T;
}
