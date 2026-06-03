#!/usr/bin/env python
"""导出 FastAPI openapi.json（不启动 uvicorn，仅构建 schema）。"""

from __future__ import annotations

import json
import os
import pathlib
import sys

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND = PROJECT_ROOT / "backend"


def main() -> None:
    if len(sys.argv) != 2:
        print(f"用法: python {sys.argv[0]} <输出路径.json>", file=sys.stderr)
        sys.exit(2)
    os.environ.setdefault("LIGHT_MAQA_FAKE_LLM", "1")
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
    sys.path.insert(0, str(BACKEND))
    # 延迟导入，确保 pythonpath / 占位 env 就绪
    from api.main import app  # noqa: E402

    out = pathlib.Path(sys.argv[1]).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    out.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
