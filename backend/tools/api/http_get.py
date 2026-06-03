"""
通用 HTTP GET（tools / api 子层）。

只读 JSON 或纯文本，小响应体；失败返回标准 ExternalEvidenceRecord 语义（status=error）。
供需要显式 REST 探测时调用，默认 middle 仍优先 fetch_url。
"""

from __future__ import annotations

from typing import Any

import httpx

from tools.standard_result import ExternalEvidenceRecord


def http_get_simple(
    url: str,
    *,
    timeout: float = 12.0,
    max_chars: int = 6000,
) -> ExternalEvidenceRecord:
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            r = client.get(
                url,
                headers={"User-Agent": "LightMAQA/1.0 (api tool)"},
            )
        r.raise_for_status()
        ct = (r.headers.get("content-type") or "").lower()
        body = r.text[:max_chars]
        if "json" in ct:
            return ExternalEvidenceRecord(
                source="http_api",
                title=url[:80],
                url=url,
                snippet=body[:500],
                content=body,
                status="ok",
                metadata={"content_type": ct},
            )
        return ExternalEvidenceRecord(
            source="http_api",
            title=url[:80],
            url=url,
            snippet=body[:500],
            content=body,
            status="ok",
            metadata={"content_type": ct or "text"},
        )
    except Exception as e:  # noqa: BLE001
        return ExternalEvidenceRecord(
            source="http_api",
            title=url[:80],
            url=url,
            status="error",
            error=str(e),
        )


def http_get_tool(**kwargs: Any) -> dict[str, Any]:
    url = str(kwargs.get("url") or "")
    rec = http_get_simple(url)
    return {
        "ok": rec.status == "ok",
        "text": rec.content,
        "error": rec.error,
        "url": rec.url,
    }
