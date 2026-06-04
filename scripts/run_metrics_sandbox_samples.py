"""
隔离沙箱：跑固定样本 + 可选双库 COUNT 对照 + 触发周报生成。

用法（仓库根）:
  $env:PYTHONPATH = "backend"
  $env:DATABASE_URL = "postgresql://light_maqa:light_maqa_dev@127.0.0.1:5433/light_maqa_metrics_sandbox"
  py -3.12 scripts/run_metrics_sandbox_samples.py --api http://127.0.0.1:8000 --report

可选主库对照:
  py -3.12 scripts/run_metrics_sandbox_samples.py --main-db postgresql://...@127.0.0.1:5432/light_maqa
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import subprocess
import sys
import time
import uuid
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

SAMPLES = REPO_ROOT / "scripts" / "metrics_sandbox_samples.yaml"


def fetch_task_result(base: str, task_id: str) -> dict:
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        f"{base.rstrip('/')}/tasks/{task_id}/result",
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body if isinstance(body, dict) else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {detail[:500]}") from e


def poll_async_final_answer(
    base: str,
    task_id: str,
    *,
    timeout_sec: float = 120.0,
    interval_sec: float = 3.0,
) -> dict:
    """async 样本：轮询 /tasks/{id}/result 直到 ready 或超时。"""
    deadline = time.perf_counter() + timeout_sec
    last: dict = {}
    while time.perf_counter() < deadline:
        last = fetch_task_result(base, task_id)
        status = str(last.get("status") or "").lower()
        if last.get("ready") and status in {"succeeded", "partial", "failed", "expired", "cancelled"}:
            return last
        if status in {"succeeded", "partial", "failed", "expired", "cancelled"}:
            return last
        time.sleep(interval_sec)
    return last


def pg_counts(database_url: str) -> dict[str, int]:
    import psycopg

    out: dict[str, int] = {}
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        for table in ("rag_chunks", "rag_embeddings", "turn_product_metrics"):
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table};")
                row = cur.fetchone()
                out[table] = int(row[0]) if row else 0
            except psycopg.Error:
                conn.rollback()
                out[table] = -1
    return out


def post_chat(
    base: str,
    message: str,
    session_id: str,
    *,
    use_knowledge: bool = False,
) -> dict:
    import urllib.error
    import urllib.request

    body = json.dumps(
        {
            "message": message,
            "session_id": session_id,
            "use_knowledge": use_knowledge,
            "confirm_long_web_video_asr": False,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}/chat/agno",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {detail[:500]}") from e


def _resolve_upload_path(item: dict) -> Path:
    raw = str(item.get("upload_file") or "").strip()
    if not raw:
        raise ValueError("upload_file missing")
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return path


def post_chat_upload(
    base: str,
    message: str,
    session_id: str,
    file_path: Path,
    *,
    upload_filename: str | None = None,
) -> dict:
    import urllib.error
    import urllib.request

    filename = (upload_filename or file_path.name).strip()
    raw = file_path.read_bytes()
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    boundary = f"----SandboxBoundary{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    def _field(name: str, value: str) -> None:
        chunks.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode(),
        )

    _field("message", message)
    _field("session_id", session_id)
    _field("use_knowledge", "false")
    _field("confirm_long_web_video_asr", "false")
    chunks.append(
        (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n"
        ).encode()
        + raw
        + b"\r\n",
    )
    chunks.append(f"--{boundary}--\r\n".encode())
    body = b"".join(chunks)
    req = urllib.request.Request(
        f"{base.rstrip('/')}/chat/agno/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {detail[:500]}") from e


def truncate_sandbox_metrics(database_url: str) -> None:
    import psycopg

    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE turn_product_metrics;")
        conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--main-db", default="", help="主库 URL，跑前后 COUNT 对照")
    parser.add_argument("--report", action="store_true", help="样本结束后生成周报 HTML")
    parser.add_argument(
        "--truncate-metrics",
        action="store_true",
        help="跑样本前清空沙箱 turn_product_metrics（洁净复跑）",
    )
    args = parser.parse_args()

    sandbox_url = __import__("os").environ.get("DATABASE_URL", "")
    if args.truncate_metrics and sandbox_url:
        truncate_sandbox_metrics(sandbox_url)
        print("SANDBOX turn_product_metrics truncated")

    main_before = pg_counts(args.main_db) if args.main_db else None
    if main_before is not None:
        print("MAIN_DB before:", main_before)

    data = yaml.safe_load(SAMPLES.read_text(encoding="utf-8"))
    results: list[dict] = []
    for item in data["samples"]:
        sid = f"sandbox_{item['id']}_{uuid.uuid4().hex[:8]}"
        t0 = time.perf_counter()
        try:
            if item.get("upload_file"):
                upload_path = _resolve_upload_path(item)
                out = post_chat_upload(
                    args.api,
                    item["message"],
                    sid,
                    upload_path,
                    upload_filename=item.get("upload_filename"),
                )
            else:
                use_kb = bool(item.get("use_knowledge"))
                out = post_chat(args.api, item["message"], sid, use_knowledge=use_kb)
            ms = int((time.perf_counter() - t0) * 1000)
            extra = out.get("extra") or {}
            row = {
                "id": item["id"],
                "tag": item["tag"],
                "message": item["message"],
                "ok": out.get("ok", True),
                "task_status": out.get("task_status"),
                "answer_summary": " ".join(str(out.get("answer") or "").split())[:320],
                "ms": ms,
                "mode": extra.get("mode"),
                "executor_profile": extra.get("executor_profile"),
                "is_complex_task": extra.get("is_complex_task"),
                "insufficient_evidence": extra.get("insufficient_evidence"),
                "quality_gate_passed": extra.get("quality_gate_passed"),
                "failure_reason_code": extra.get("failure_reason_code"),
                "complex_candidate": extra.get("complex_candidate"),
                "complex_reason_codes": extra.get("complex_reason_codes"),
                "pending_kind": extra.get("pending_kind"),
                "video_task_id": extra.get("video_task_id"),
                "web_task_id": extra.get("web_task_id") or extra.get("task_id"),
                "upload_file": item.get("upload_file"),
                "use_knowledge": bool(item.get("use_knowledge")),
            }
            if item.get("tag") == "async":
                task_id = str(out.get("task_id") or extra.get("web_task_id") or "").strip()
                if task_id:
                    try:
                        polled = poll_async_final_answer(args.api, task_id)
                        result = polled.get("result") if isinstance(polled.get("result"), dict) else {}
                        final_answer = str(
                            (result or {}).get("final_answer")
                            or (result or {}).get("answer")
                            or ""
                        ).strip()
                        poll_status = str(polled.get("status") or "").strip() or None
                        bg_ms = polled.get("task_enqueue_to_finish_ms")
                        err_obj = polled.get("error") if isinstance(polled.get("error"), dict) else {}
                        err_msg = str(
                            err_obj.get("message")
                            or polled.get("failure_reason")
                            or polled.get("error_code")
                            or ""
                        ).strip()
                        if not final_answer and poll_status in {"failed", "expired", "cancelled"}:
                            final_answer = (
                                f"⚠️ 后台抓取失败：{err_msg or '动态页超时或无法解析正文'}"
                            )
                        if final_answer:
                            row["async_final_answer"] = final_answer[:1500]
                            row["answer_summary"] = final_answer[:1500]
                        if err_msg:
                            row["async_poll_error"] = err_msg[:200]
                        row["async_poll_status"] = poll_status
                        row["async_background_ms"] = bg_ms
                        from storage.turn_product_metrics_pg import (
                            update_turn_product_metrics_async_completion,
                        )

                        update_turn_product_metrics_async_completion(
                            task_id=task_id,
                            async_final_answer=final_answer or None,
                            async_poll_status=poll_status,
                            async_background_ms=int(bg_ms) if bg_ms is not None else None,
                            answer_summary=row.get("answer_summary"),
                        )
                    except (RuntimeError, OSError, ValueError) as poll_exc:  # noqa: BLE001
                        row["async_poll_error"] = str(poll_exc)[:200]
            line = json.dumps(row, ensure_ascii=False)
            sys.stdout.buffer.write(line.encode("utf-8", errors="replace") + b"\n")
            results.append(row)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {item['id']}: {exc}", file=sys.stderr)
            results.append({"id": item["id"], "error": str(exc)})

    sandbox_counts: dict[str, int] | None = None
    if sandbox_url:
        sandbox_counts = pg_counts(sandbox_url)
        print("SANDBOX counts:", sandbox_counts)

    if main_before is not None and args.main_db:
        main_after = pg_counts(args.main_db)
        print("MAIN_DB after:", main_after)
        polluted = any(main_after.get(k) != main_before.get(k) for k in main_before)
        print("MAIN_DB polluted:", polluted)

    sample_n = len(data["samples"])
    metrics_n = sandbox_counts.get("turn_product_metrics", -1) if sandbox_counts else -1
    if metrics_n >= 0:
        print(f"METRICS rows vs samples: {metrics_n}/{sample_n}")
        if metrics_n != sample_n:
            print("WARN: turn_product_metrics count != sample count", file=sys.stderr)

    tag_checks: list[str] = []
    for item, row in zip(data["samples"], results, strict=False):
        if row.get("error"):
            continue
        tag = item.get("tag")
        if tag == "complex" and not row.get("is_complex_task"):
            tag_checks.append(f"{item['id']}: expected is_complex_task=true")
        if tag == "async" and str(row.get("executor_profile") or "").lower() != "async":
            tag_checks.append(
                f"{item['id']}: expected executor_profile=async got {row.get('executor_profile')!r}"
            )
    if tag_checks:
        print("TAG validation failures:", file=sys.stderr)
        for line in tag_checks:
            print(f"  - {line}", file=sys.stderr)
    else:
        print("TAG validation: ok")

    if args.report:
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "report_product_metrics.py"), "--days", "7", "--html"],
            check=False,
            env=__import__("os").environ.copy(),
        )

    failed = sum(1 for r in results if r.get("error"))
    if tag_checks:
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
