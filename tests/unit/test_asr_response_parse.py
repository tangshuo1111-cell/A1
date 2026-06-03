"""Regression for tools.asr.response_parse (split from providers)."""

from __future__ import annotations

from tools.asr.response_parse import (
    parse_http_asr_json,
    parse_tencent_asr_json,
    parse_tencent_flash_asr_json,
)


def test_parse_http_nested_result_segments() -> None:
    payload = {"result": {"text": "", "segments": [{"text": "a", "start": 1, "end": 2}]}}
    full, segments, err = parse_http_asr_json(payload)
    assert err is None
    assert full == "a"
    assert len(segments) == 1
    assert segments[0]["text"] == "a"


def test_parse_tencent_error_shape() -> None:
    data = {"Response": {"Error": {"Code": "AuthFailure", "Message": "sig"}}}
    _, _, code, msg = parse_tencent_asr_json(data)
    assert code == "AuthFailure"
    assert msg == "sig"


def test_parse_tencent_flash_code_nonzero() -> None:
    data = {"code": 40003, "message": "oops"}
    _, _, code, msg = parse_tencent_flash_asr_json(data)
    assert code == "40003"
    assert "oops" in msg
