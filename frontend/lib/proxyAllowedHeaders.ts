/**
 * Headers allowed to pass through the Next.js /api-proxy route (Round 12).
 * Do not forward arbitrary browser headers to the backend.
 */
const ALLOWED_REQUEST_HEADERS = new Set(
  [
    "authorization",
    "content-type",
    "accept",
    "accept-language",
    "x-request-id",
    "x-session-id",
    "x-admin-key",
  ].map((h) => h.toLowerCase()),
);

export function isProxyAllowedRequestHeader(name: string): boolean {
  return ALLOWED_REQUEST_HEADERS.has(name.toLowerCase());
}

export function copyAllowedProxyRequestHeaders(
  source: Headers,
): Headers {
  const headers = new Headers();
  source.forEach((value, key) => {
    if (isProxyAllowedRequestHeader(key)) {
      headers.set(key, value);
    }
  });
  return headers;
}
