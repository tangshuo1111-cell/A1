from __future__ import annotations

import os
import sys
from pathlib import Path

from python_runtime import collect_runtime_report
from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

# 触发 .env 加载（与运行时一致）
import config.settings  # noqa: E402,F401


def _env_files_checked() -> list[Path]:
    candidates = [ROOT / ".env"]
    for parent in ROOT.parents[:3]:
        candidates.append(parent / ".env")
    seen: set[Path] = set()
    loaded: list[Path] = []
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if path.exists():
            loaded.append(path)
    return loaded


def main() -> int:
    required_paths = [
        ROOT / "backend",
        ROOT / "frontend",
        ROOT / "_local",
        ROOT / "data" / "samples" / "knowledge",
        ROOT / "data" / "samples" / "web",
    ]
    for path in required_paths:
        print(f"{'OK' if path.exists() else 'MISSING'}  {path}")

    env_files = _env_files_checked()
    if env_files:
        print("ENV files:")
        for path in env_files:
            print(f"  LOADED  {path}")
    else:
        print("ENV files: none found (copy .env.example -> .env)")

    runtime_report = collect_runtime_report()
    print(f"selected_python={runtime_report['selected_python']}")
    if runtime_report["warnings"]:
        print("Python runtime warnings:")
        for item in runtime_report["warnings"]:
            print(f"  - {item}")

    keys = [
        "OPENAI_API_KEY",
        "LLM_API_KEY",
        "V16_WEB_SEARCH_API_KEY",
        "TAVILY_API_KEY",
        "V16_TENCENT_SECRET_ID",
        "V16_TENCENT_SECRET_KEY",
    ]
    for key in keys:
        present = bool((os.environ.get(key) or "").strip())
        print(f"{key}={'SET' if present else 'EMPTY'}")

    from config.settings import settings

    wp = (settings.v16_web_search_provider or "").strip()
    sp = (settings.v16_search_provider or "").strip()
    ak = bool((settings.v16_web_search_api_key or "").strip())
    effective = wp or sp
    print(f"V16_WEB_SEARCH_PROVIDER(resolved)={wp or 'EMPTY'}")
    print(f"V16_SEARCH_PROVIDER={sp or 'EMPTY'}")
    print(f"v16_web_search_api_key(resolved)={'SET' if ak else 'EMPTY'}")
    if effective and ak:
        print(f"web_search_effective={effective} (ready)")
    elif effective and not ak:
        print(f"web_search_effective={effective} (missing API key)")
    elif ak and not effective:
        print("web_search_effective=EMPTY (key present but no provider — should not happen)")
    else:
        print("web_search_effective=ddg_html_fallback (no Tavily; CRAG fetch_web uses DuckDuckGo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
