#!/usr/bin/env python
"""
统一本地开发启动脚本。

用法：
    python scripts/run_dev.py --backend              # 默认 1 worker + uvicorn --reload
    python scripts/run_dev.py --backend --workers 4  # 多 worker（关闭 reload，近似生产形态）
    python scripts/run_dev.py --frontend    # 启动前端 dev server
    python scripts/run_dev.py --all         # 同时启动（与单独 --backend 相同默认参数）
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from python_runtime import resolve_python_bin
from utf8_console import configure_utf8_stdio

configure_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_backend(*, workers: int) -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "backend")
    python_bin = resolve_python_bin()
    cmd: list[str] = [
        str(python_bin),
        "-m",
        "uvicorn",
        "api.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]
    if workers > 1:
        cmd.extend(["--workers", str(workers)])
        print("[run_dev] Backend: multi-worker mode (reload disabled)")
    else:
        cmd.append("--reload")
        print("[run_dev] Backend: reload + single worker (dev default)")
    return subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
    )


def run_frontend() -> subprocess.Popen:
    frontend_dir = PROJECT_ROOT / "frontend"
    return subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=str(frontend_dir),
        shell=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="本地开发启动")
    parser.add_argument("--backend", action="store_true", help="启动后端")
    parser.add_argument("--frontend", action="store_true", help="启动前端")
    parser.add_argument("--all", action="store_true", help="同时启动")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="uvicorn worker 数量；默认 1 且启用 --reload。>1 时关闭 reload（Docker/压测用法见 Dockerfile）",
    )
    args = parser.parse_args()

    if not (args.backend or args.frontend or args.all):
        args.all = True

    procs: list[subprocess.Popen] = []

    if args.backend or args.all:
        w = args.workers
        if w < 1:
            parser.error("--workers must be >= 1")
        print("[run_dev] Starting backend on :8000 ...")
        procs.append(run_backend(workers=w))

    if args.frontend or args.all:
        print("[run_dev] Starting frontend on :3000 ...")
        procs.append(run_frontend())

    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("\n[run_dev] Stopping...")
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
