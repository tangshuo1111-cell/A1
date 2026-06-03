"""Tencent ASR signing helpers (TC3 + Flash HMAC). Split from providers for clarity."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac

TENCENT_ASR_HOST = "asr.tencentcloudapi.com"
TENCENT_ASR_VERSION = "2019-06-14"
TENCENT_ASR_ACTION = "SentenceRecognition"
TENCENT_FLASH_ASR_HOST = "asr.cloud.tencent.com"


def tencent_tc3_headers(
    *,
    secret_id: str,
    secret_key: str,
    service: str,
    host: str,
    action: str,
    version: str,
    region: str,
    payload: str,
    timestamp: int,
) -> dict[str, str]:
    algorithm = "TC3-HMAC-SHA256"
    date = dt.datetime.fromtimestamp(timestamp, tz=dt.UTC).strftime("%Y-%m-%d")
    canonical_headers = (
        "content-type:application/json; charset=utf-8\n"
        f"host:{host}\n"
        f"x-tc-action:{action.lower()}\n"
    )
    signed_headers = "content-type;host;x-tc-action"
    hashed_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = "\n".join(
        ["POST", "/", "", canonical_headers, signed_headers, hashed_payload]
    )
    credential_scope = f"{date}/{service}/tc3_request"
    hashed_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = "\n".join([algorithm, str(timestamp), credential_scope, hashed_request])

    def sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    secret_date = sign(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = sign(secret_date, service)
    secret_signing = sign(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = (
        f"{algorithm} Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "Authorization": authorization,
        "Content-Type": "application/json; charset=utf-8",
        "Host": host,
        "X-TC-Action": action,
        "X-TC-Version": version,
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Region": region,
    }


def tencent_flash_signature(
    *,
    appid: str,
    secret_key: str,
    params: dict[str, str],
) -> str:
    query = "&".join(f"{k}={params[k]}" for k in sorted(params))
    plain = f"POST{TENCENT_FLASH_ASR_HOST}/asr/flash/v1/{appid}?{query}"
    digest = hmac.new(
        secret_key.encode("utf-8"),
        plain.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode("ascii")
