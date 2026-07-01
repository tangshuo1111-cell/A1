"""
隔离沙箱：跑固定样本 + 可选双库 COUNT 对照 + 触发周报生成。

用法（仓库根）:
  $env:DATABASE_URL = "postgresql://light_maqa:light_maqa_dev@127.0.0.1:5433/light_maqa_metrics_sandbox"
  python scripts/run_metrics_sandbox_samples.py --api http://127.0.0.1:8001 --report
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
REUSE_ASSET = REPO_ROOT / "scripts" / "metrics_sandbox_assets" / "phoenix_brief.md"
REUSE_SOURCE_ID = "metrics_sandbox/phoenix_brief.md"
DEFAULT_CHAT_TIMEOUT_SEC = float(
    __import__("os").environ.get("SANDBOX_CHAT_TIMEOUT_SEC", "120")
)
COMPLEX_CHAT_TIMEOUT_SEC = float(
    __import__("os").environ.get("SANDBOX_COMPLEX_CHAT_TIMEOUT_SEC", "240")
)
ASYNC_POLL_TIMEOUT_SEC = float(
    __import__("os").environ.get("SANDBOX_ASYNC_POLL_TIMEOUT_SEC", "240")
)


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
    timeout_sec: float = DEFAULT_CHAT_TIMEOUT_SEC,
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
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {detail[:500]}") from e


def _resolve_asset_path(item: dict) -> Path:
    raw = str(item.get("asset_file") or REUSE_ASSET.relative_to(REPO_ROOT)).strip()
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return path


def run_commit_then_retrieve_flow(
    base: str,
    item: dict,
    session_id: str,
) -> tuple[dict, dict[str, bool]]:
    """upload prepare → commit → retrieve（全 API，同 session）。"""
    asset = _resolve_asset_path(item)
    upload_name = str(item.get("upload_filename") or asset.name).strip()
    prep = post_chat_upload(
        base,
        str(item.get("prepare_message") or "请先解析这份资料。"),
        session_id,
        asset,
        upload_filename=upload_name,
    )
    prep_extra = prep.get("extra") or {}
    prepare_ok = (
        prep_extra.get("v13_material_status") == "pending"
        or (
            prep_extra.get("pending_kind") == "material_pending"
            and bool(prep_extra.get("pending_source_id"))
        )
    )
    commit = post_chat(base, str(item.get("commit_message") or "保存到知识库"), session_id)
    commit_extra = commit.get("extra") or {}
    commit_ok = commit_extra.get("commit_success") is True or (
        commit.get("answer_type") == "commit_executed"
        and commit.get("task_status") == "succeeded"
        and commit_extra.get("approval_gate.executed") is True
    )
    retrieve = post_chat(
        base,
        str(item.get("retrieve_message") or item.get("message") or ""),
        session_id,
        use_knowledge=True,
    )
    return retrieve, {"flow_prepare_ok": prepare_ok, "flow_commit_ok": commit_ok}


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


def seed_committed_reuse_corpus() -> int:
    """Seed 沙箱 KB：user_committed 代表资料（北极星1 分母/分子观测）。"""
    if not REUSE_ASSET.is_file():
        raise FileNotFoundError(f"reuse asset missing: {REUSE_ASSET}")
    from rag.retrieval_provenance import SOURCE_KIND_USER_COMMITTED
    from storage import knowledge_store

    knowledge_store.ensure_ready()
    text = REUSE_ASSET.read_text(encoding="utf-8")
    chunks = knowledge_store.save_document_text(
        text,
        source_id=REUSE_SOURCE_ID,
        source_type="text_file",
        title="Phoenix Brief (metrics sandbox)",
        extra_metadata={"source_kind": SOURCE_KIND_USER_COMMITTED},
    )
    return int(chunks)


def expected_metric_rows(samples: list[dict]) -> int:
    total = 0
    for item in samples:
        if str(item.get("flow") or "") == "commit_then_retrieve":
            total += 3
        else:
            total += 1
    return total


def _row_from_response(item: dict, out: dict, *, ms: int) -> dict:
    extra = out.get("extra") or {}
    row = {
        "id": item["id"],
        "tag": item.get("tag"),
        "message": item.get("message") or item.get("retrieve_message") or "",
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
        "user_committed_retrieval_hit": bool(extra.get("user_committed_retrieval_hit")),
        "v15_retrieved_chunks_count": int(extra.get("v15_retrieved_chunks_count") or 0),
    }
    from application.analytics.metrics_diagnostic import enrich_metrics_diagnostic_row

    return enrich_metrics_diagnostic_row(row, extra)


def _append_observation_ledger(*, breakdown: dict, api: str, use_pg_canonical: bool = False) -> None:
    """Append-only REAL/FAKE sandbox observation log (gitignored _local).

    north_star2 真源与周报一致：use_pg_canonical 时读 turn_product_metrics 聚合（product_metrics）。
    breakdown 的 complex_partial 仍来自 yaml 样本诊断层。
    """
    import subprocess as _sp

    os_mod = __import__("os")
    fake = str(os_mod.environ.get("LIGHT_MAQA_FAKE_LLM", "")).strip().lower() in {"1", "true", "yes", "on"}
    refine_env = str(os_mod.environ.get("ENABLE_COMPLEX_REFINE_V2", "")).strip().lower()
    if refine_env in {"0", "false", "off", "no"}:
        refine_mode = "off"
    elif refine_env in {"1", "true", "on", "yes"}:
        refine_mode = "on"
    else:
        refine_mode = "default"
    git_rev = ""
    try:
        git_rev = _sp.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT),
            text=True,
            stderr=_sp.DEVNULL,
        ).strip()
    except (OSError, _sp.CalledProcessError):
        git_rev = "unknown"
    complex_partial = int(breakdown.get("complex_partial") or 0)
    complex_total = int(breakdown.get("complex_total") or 0)
    effective_rate = None
    if use_pg_canonical and not fake:
        from datetime import UTC, datetime, timedelta

        from application.analytics.product_metrics import aggregate_turn_rows
        from storage.turn_product_metrics_pg import fetch_metrics_between

        cur_end = datetime.now(UTC)
        cur_start = cur_end - timedelta(days=7)
        pg_rows = fetch_metrics_between(cur_start, cur_end)
        agg = aggregate_turn_rows(pg_rows)
        complex_total = int(agg.get("complex_task_count") or 0)
        rate_val = agg.get("complex_effective_complete_rate")
        if complex_total > 0 and rate_val is not None:
            effective_rate = round(float(rate_val), 4)
    if effective_rate is None and complex_total > 0:
        eff = breakdown.get("complex_effective_succeeded")
        if eff is not None:
            effective_rate = round(int(eff) / complex_total, 4)
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "git_rev": git_rev,
        "environment": "FAKE" if fake else "REAL",
        "api": api,
        "db": "light_maqa_metrics_sandbox@5433",
        "refine_v2": refine_mode,
        "complex_total": complex_total,
        "complex_partial": complex_partial,
        "north_star2": effective_rate,
        "north_star2_source": "product_metrics" if use_pg_canonical and not fake else "yaml_diagnostic",
        "counts_for_dod": (not fake) and refine_mode == "on" and "8001" in api,
    }
    ledger_dir = REPO_ROOT / "_local" / "reports" / "metrics"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = ledger_dir / "observation_ledger.jsonl"
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"LEDGER: {json.dumps(entry, ensure_ascii=False)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--report", action="store_true", help="样本结束后生成周报 HTML")
    parser.add_argument(
        "--truncate-metrics",
        action="store_true",
        help="跑样本前清空沙箱 turn_product_metrics（洁净复跑）",
    )
    args = parser.parse_args()

    fake_llm = __import__("os").environ.get("LIGHT_MAQA_FAKE_LLM", "")
    if str(fake_llm).strip().lower() in {"1", "true", "yes"}:
        print(
            "WARN: LIGHT_MAQA_FAKE_LLM=1 — 北极星2 有效完成率在 FAKE 下不可外推（见 KI-METRICS-001）",
            file=sys.stderr,
        )

    sandbox_url = __import__("os").environ.get("DATABASE_URL", "")
    if args.truncate_metrics and sandbox_url:
        truncate_sandbox_metrics(sandbox_url)
        print("SANDBOX turn_product_metrics truncated")

    try:
        seeded = seed_committed_reuse_corpus()
        print(f"SANDBOX reuse seed OK source_id={REUSE_SOURCE_ID} chunks={seeded}")
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: reuse seed failed: {exc}", file=sys.stderr)

    data = yaml.safe_load(SAMPLES.read_text(encoding="utf-8"))
    samples: list[dict] = list(data["samples"])
    results: list[dict] = []
    shadow_mismatches: list[dict] = []
    for item in samples:
        sid = f"sandbox_{item['id']}_{uuid.uuid4().hex[:8]}"
        t0 = time.perf_counter()
        try:
            flow = str(item.get("flow") or "")
            flow_meta: dict[str, bool] = {}
            if flow == "commit_then_retrieve":
                out, flow_meta = run_commit_then_retrieve_flow(args.api, item, sid)
            elif item.get("upload_file"):
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
                chat_timeout = (
                    COMPLEX_CHAT_TIMEOUT_SEC
                    if str(item.get("tag") or "").strip().lower() == "complex"
                    else DEFAULT_CHAT_TIMEOUT_SEC
                )
                out = post_chat(
                    args.api,
                    item["message"],
                    sid,
                    use_knowledge=use_kb,
                    timeout_sec=chat_timeout,
                )
            ms = int((time.perf_counter() - t0) * 1000)
            row = _row_from_response(item, out, ms=ms)
            row.update(flow_meta)
            trace = (out.get("extra") or {}).get("trace") or {}
            shadow = trace.get("exit_shadow") or {}
            if shadow and not shadow.get("match"):
                shadow_mismatches.append(
                    {"id": item["id"], "diff_fields": shadow.get("diff_fields") or {}}
                )
            if item.get("tag") == "async":
                extra = out.get("extra") or {}
                task_id = str(out.get("task_id") or extra.get("web_task_id") or "").strip()
                if task_id:
                    try:
                        polled = poll_async_final_answer(
                            args.api,
                            task_id,
                            timeout_sec=ASYNC_POLL_TIMEOUT_SEC,
                        )
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

    sample_n = len(samples)
    expected_rows = expected_metric_rows(samples)
    metrics_n = sandbox_counts.get("turn_product_metrics", -1) if sandbox_counts else -1
    if metrics_n >= 0:
        print(f"METRICS rows vs samples: {metrics_n}/{expected_rows} (yaml cases={sample_n})")
        if metrics_n != expected_rows:
            print("WARN: turn_product_metrics count != expected metric turns", file=sys.stderr)

    tag_checks: list[str] = []
    for item, row in zip(samples, results, strict=False):
        if row.get("error"):
            continue
        tag = item.get("tag")
        if tag == "complex" and not row.get("is_complex_task"):
            tag_checks.append(f"{item['id']}: expected is_complex_task=true")
        if tag == "async" and str(row.get("executor_profile") or "").lower() != "async":
            tag_checks.append(
                f"{item['id']}: expected executor_profile=async got {row.get('executor_profile')!r}"
            )
        if tag == "reuse":
            if str(item.get("flow") or "") == "commit_then_retrieve":
                if not row.get("flow_prepare_ok"):
                    tag_checks.append(f"{item['id']}: expected flow_prepare_ok=true")
                if not row.get("flow_commit_ok"):
                    tag_checks.append(f"{item['id']}: expected flow_commit_ok=true")
            if int(row.get("v15_retrieved_chunks_count") or 0) <= 0:
                tag_checks.append(f"{item['id']}: expected retrieval hits for reuse sample")
            elif not row.get("user_committed_retrieval_hit"):
                tag_checks.append(f"{item['id']}: expected user_committed_retrieval_hit=true")
    if tag_checks:
        print("TAG validation failures:", file=sys.stderr)
        for line in tag_checks:
            print(f"  - {line}", file=sys.stderr)
    else:
        print("TAG validation: ok")

    shadow_on = str(__import__("os").environ.get("ENABLE_TURN_EXIT_GATE_SHADOW", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if shadow_on:
        if shadow_mismatches:
            print("EXIT_SHADOW mismatches:", file=sys.stderr)
            for entry in shadow_mismatches:
                print(f"  - {entry['id']}: {entry['diff_fields']}", file=sys.stderr)
        else:
            print("EXIT_SHADOW: ok (all match)")

    from application.analytics.metrics_diagnostic import (
        build_complex_failure_breakdown,
        render_diagnostic_summary_lines,
    )

    breakdown = build_complex_failure_breakdown(results)
    complex_eff = sum(
        1
        for r in results
        if r.get("is_complex_task")
        and str(r.get("task_status") or "").lower() == "succeeded"
        and not r.get("insufficient_evidence")
        and r.get("quality_gate_passed") is not False
    )
    breakdown["complex_effective_succeeded"] = complex_eff
    for line in render_diagnostic_summary_lines(breakdown):
        print(f"DIAG: {line}")
    diag_dir = REPO_ROOT / "_local" / "reports" / "metrics"
    diag_dir.mkdir(parents=True, exist_ok=True)
    diag_path = diag_dir / "last_sandbox_diagnostic.json"
    diag_path.write_text(
        json.dumps({"breakdown": breakdown, "rows": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if args.report:
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "report_product_metrics.py"), "--days", "7", "--html"],
            check=False,
            env=__import__("os").environ.copy(),
        )

    _append_observation_ledger(
        breakdown=breakdown,
        api=str(args.api),
        use_pg_canonical=bool(args.report),
    )

    failed = sum(1 for r in results if r.get("error"))
    if tag_checks or shadow_mismatches:
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
