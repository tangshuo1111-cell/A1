"""
第五轮联调：轻量 stderr 追踪（不引入日志框架）。

启用方式：命令行传入 --trace（由 app.py 打开）。
"""

from __future__ import annotations

import sys

enabled: bool = False


def set_enabled(value: bool) -> None:
    global enabled
    enabled = value


def trace(message: str) -> None:
    if enabled:
        print(f"[trace] {message}", file=sys.stderr, flush=True)
