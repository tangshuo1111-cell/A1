"""ASR provider JSON response parsers (no HTTP)."""

from __future__ import annotations

from typing import Any

from tools.asr import errors as asr_errors


def parse_http_asr_json(data: Any) -> tuple[str, list[dict[str, Any]], str | None]:
    if not isinstance(data, dict):
        return "", [], asr_errors.ASR_INVALID_RESPONSE
    text_top = str(data.get("text") or "").strip()
    segs_raw = data.get("segments")
    inner = data.get("result")
    if isinstance(inner, dict) and not text_top:
        text_top = str(inner.get("text") or "").strip()
        if not isinstance(segs_raw, list) and inner.get("segments"):
            segs_raw = inner.get("segments")
    norm: list[dict[str, Any]] = []
    if isinstance(segs_raw, list):
        for s in segs_raw:
            if not isinstance(s, dict):
                continue
            t = str(s.get("text") or "").strip()
            if not t:
                continue
            try:
                st = float(s.get("start", 0.0))
                en = float(s.get("end", 0.0))
            except (TypeError, ValueError):
                st, en = 0.0, 0.0
            norm.append({"start_time": st, "end_time": en, "text": t})
    full = text_top
    if not full and norm:
        full = "\n".join(x["text"] for x in norm).strip()
    if not full:
        return "", norm, asr_errors.ASR_EMPTY_RESULT
    return full, norm, None


def parse_tencent_asr_json(data: Any) -> tuple[str, list[dict[str, Any]], str | None, str]:
    if not isinstance(data, dict):
        return "", [], asr_errors.ASR_INVALID_RESPONSE, ""
    resp = data.get("Response")
    if not isinstance(resp, dict):
        return "", [], asr_errors.ASR_INVALID_RESPONSE, ""
    err = resp.get("Error")
    if isinstance(err, dict):
        code = str(err.get("Code") or asr_errors.ASR_PROVIDER_ERROR)
        msg = str(err.get("Message") or "Tencent ASR provider error")
        return "", [], code, msg
    text = str(resp.get("Result") or "").strip()
    if not text:
        return "", [], asr_errors.ASR_EMPTY_RESULT, "Tencent ASR returned no text"
    return text, [{"start_time": 0.0, "end_time": 0.0, "text": text}], None, ""


def parse_tencent_flash_asr_json(data: Any) -> tuple[str, list[dict[str, Any]], str | None, str]:
    if not isinstance(data, dict):
        return "", [], asr_errors.ASR_INVALID_RESPONSE, ""
    code = data.get("code")
    if code not in (0, "0", None):
        msg = str(data.get("message") or "Tencent Flash ASR provider error")
        return "", [], str(code or asr_errors.ASR_PROVIDER_ERROR), msg
    results = data.get("flash_result")
    if not isinstance(results, list):
        return (
            "",
            [],
            asr_errors.ASR_INVALID_RESPONSE,
            "Tencent Flash ASR response missing flash_result",
        )

    segments: list[dict[str, Any]] = []
    parts: list[str] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        channel_text = str(item.get("text") or "").strip()
        sentences = item.get("sentence_list")
        if isinstance(sentences, list):
            for sentence in sentences:
                if not isinstance(sentence, dict):
                    continue
                text = str(sentence.get("text") or "").strip()
                if not text:
                    continue
                try:
                    start = float(sentence.get("start_time", 0.0)) / 1000.0
                    end = float(sentence.get("end_time", 0.0)) / 1000.0
                except (TypeError, ValueError):
                    start, end = 0.0, 0.0
                segments.append({"start_time": start, "end_time": end, "text": text})
                parts.append(text)
        elif channel_text:
            parts.append(channel_text)
    text = "\n".join(parts).strip()
    if not text:
        return "", segments, asr_errors.ASR_EMPTY_RESULT, "Tencent Flash ASR returned no text"
    return text, segments or [{"start_time": 0.0, "end_time": 0.0, "text": text}], None, ""
