"""比较两份 openapi JSON 是否等价（按键排序规范化，忽略空白差异）。"""

from __future__ import annotations

import json
import pathlib
import sys

from utf8_console import configure_utf8_stdio

configure_utf8_stdio()


def _canon(raw: bytes) -> str:
    data = json.loads(raw.decode("utf-8"))
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def main() -> None:
    if len(sys.argv) != 3:
        print(
            "用法: python check_openapi_parity.py <已提交路径> <刚生成路径>",
            file=sys.stderr,
        )
        sys.exit(2)
    p1, p2 = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    if _canon(p1.read_bytes()) != _canon(p2.read_bytes()):
        print(
            "openapi drift: docs/current/openapi.json 与当前路由不一致。\n"
            "请在 项目代码 根目录运行：\n"
            "  PYTHONPATH=backend LIGHT_MAQA_FAKE_LLM=1 python scripts/export_openapi.py docs/current/openapi.json",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
