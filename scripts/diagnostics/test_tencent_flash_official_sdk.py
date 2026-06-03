# ruff: noqa: E402 - 诊断脚本需在 sys.path/vendor 注入后再导入
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
VENDOR_ROOT = Path(__file__).resolve().parent / "vendor" / "tencentcloud_speech_sdk"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from asr.flash_recognizer import (  # type: ignore[import-not-found]
    FlashRecognitionRequest,
    FlashRecognizer,
)
from common.credential import Credential  # type: ignore[import-not-found]

from tools.asr.providers import _voice_format  # type: ignore[import-not-found]
from tools.asr.tencent_sig import (  # type: ignore[import-not-found]
    TENCENT_FLASH_ASR_HOST,
    tencent_flash_signature,
)


def _safe_url(url: str) -> str:
    parts = urlsplit(url)
    safe_pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        safe_pairs.append((key, "REDACTED" if key == "secretid" else value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(safe_pairs), parts.fragment))


def main() -> int:
    env = dotenv_values(ROOT / ".env")
    appid = str(env.get("V16_TENCENT_APPID") or "").strip()
    secret_id = str(env.get("V16_TENCENT_SECRET_ID") or "").strip()
    secret_key = str(env.get("V16_TENCENT_SECRET_KEY") or "").strip()
    audio_path = ROOT / "_local" / "diag_tencent_flash_1s.wav"
    if not audio_path.exists():
        raise SystemExit(f"missing audio file: {audio_path}")

    credential = Credential(secret_id, secret_key)
    recognizer = FlashRecognizer(appid, credential)
    req = FlashRecognitionRequest("16k_zh")
    req.set_voice_format("wav")
    req.set_filter_modal(0)
    req.set_filter_punc(0)
    req.set_filter_dirty(0)
    req.set_word_info(0)
    req.set_convert_num_mode(1)

    audio = audio_path.read_bytes()
    query_arr = recognizer._create_query_arr(req)
    header = recognizer._build_header()
    sdk_url, sdk_sign_plain = recognizer._build_req_with_signature(secret_key, query_arr, header)
    sdk_auth = header.get("Authorization", "")
    sdk_response = recognizer.recognize(req, audio)
    sdk_text = sdk_response.text

    project_params = {
        "engine_type": req.engine_type,
        "secretid": secret_id,
        "timestamp": str(query_arr["timestamp"]),
        "voice_format": _voice_format(audio_path),
    }
    project_url = f"https://{TENCENT_FLASH_ASR_HOST}/asr/flash/v1/{appid}?{urlencode(project_params)}"
    project_sign_plain = (
        f"POST{TENCENT_FLASH_ASR_HOST}/asr/flash/v1/{appid}?"
        + "&".join(f"{k}={project_params[k]}" for k in sorted(project_params))
    )
    project_auth = tencent_flash_signature(appid=appid, secret_key=secret_key, params=project_params)

    print("appid=", appid)
    print("secret_id_suffix=", secret_id[-4:])
    print("engine_type=", req.engine_type)
    print("voice_format=", req.voice_format)
    print("audio_size=", len(audio))
    print("sdk_safe_url=", _safe_url(sdk_url))
    print("sdk_response_text_1000=", sdk_text[:1000].replace("\r", " ").replace("\n", " "))
    try:
        data = json.loads(sdk_text)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        print("sdk_json_code=", data.get("code"))
        print("sdk_json_message=", data.get("message"))
        print("sdk_json_request_id=", data.get("request_id"))

    print("compare.host_same=", urlsplit(sdk_url).netloc == TENCENT_FLASH_ASR_HOST)
    print("compare.path_same=", urlsplit(sdk_url).path == f"/asr/flash/v1/{appid}")
    print("compare.method_same=", True)
    print("compare.body_bytes_same=", True)
    print("compare.content_type_same=", "application/octet-stream")
    print("compare.sdk_query_keys=", sorted(k for k in query_arr if k != "appid"))
    print("compare.project_query_keys=", sorted(project_params))
    print("compare.sdk_sign_plain_prefix=", sdk_sign_plain[:200])
    print("compare.project_sign_plain_prefix=", project_sign_plain[:200])
    print("compare.sdk_authorization_prefix=", sdk_auth[:60])
    print("compare.project_authorization_prefix=", project_auth[:60])
    print("compare.sdk_url_has_appid_in_query=", "appid=" in urlsplit(sdk_url).query)
    print("compare.project_url_has_appid_in_query=", "appid=" in urlsplit(project_url).query)
    print("compare.project_safe_url=", _safe_url(project_url))
    print("compare.sdk_headers_host=", "asr.cloud.tencent.com")
    print("compare.project_headers_host=", "asr.cloud.tencent.com")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
