from __future__ import annotations

import os
from pathlib import Path

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    required_paths = [
        root / "backend",
        root / "frontend",
        root / "_local",
        root / "data" / "samples" / "knowledge",
        root / "data" / "samples" / "web",
    ]
    for path in required_paths:
        print(f"{'OK' if path.exists() else 'MISSING'}  {path}")

    keys = [
        "OPENAI_API_KEY",
        "LLM_API_KEY",
        "V16_WEB_SEARCH_API_KEY",
        "V16_TENCENT_SECRET_ID",
        "V16_TENCENT_SECRET_KEY",
    ]
    for key in keys:
        present = bool((os.environ.get(key) or "").strip())
        print(f"{key}={'SET' if present else 'EMPTY'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
