from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
from utf8_console import configure_utf8_stdio  # noqa: E402 - sys.path 注入后才能导入

configure_utf8_stdio()

import requests  # noqa: E402 - 在 utf8 stdio 配置后导入


def load_questions(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _result_from_payload(
    *,
    qid: str,
    prompt: str,
    elapsed: float,
    data: dict[str, Any],
    http_status: int = 200,
) -> dict[str, Any]:
    extra = data.get("extra") or {}
    return {
        "id": qid,
        "question": prompt,
        "http_status": http_status,
        "elapsed_s": elapsed,
        "answer": data.get("answer", ""),
        "answer_type": data.get("answer_type"),
        "primary_path": data.get("primary_path"),
        "task_status": data.get("task_status"),
        "extra": {
            "mode": extra.get("mode"),
            "router_lane": extra.get("router_lane"),
            "agent_timings": extra.get("agent_timings"),
            "capabilities_called": extra.get("capabilities_called"),
            "router_source": extra.get("router_source"),
            "router_confidence": extra.get("router_confidence"),
            "remaining_ms": extra.get("remaining_ms"),
            "answer_llm_metrics": {
                "prompt_chars": extra.get("answer_llm.prompt_chars"),
                "answer_chars": extra.get("answer_llm.answer_chars"),
                "knowledge_chars": extra.get("answer_llm.knowledge_chars"),
                "web_chars": extra.get("answer_llm.web_chars"),
                "hint_chars": extra.get("answer_llm.hint_chars"),
                "prompt_tokens_est": extra.get("answer_llm.prompt_tokens_est"),
                "answer_tokens_est": extra.get("answer_llm.answer_tokens_est"),
                "prompt_tokens": extra.get("answer_llm.prompt_tokens"),
                "answer_tokens": extra.get("answer_llm.answer_tokens"),
                "total_tokens": extra.get("answer_llm.total_tokens"),
            } if any(k.startswith("answer_llm.") for k in extra) else None,
        },
    }


def run_questions_http(*, base_url: str, questions: list[dict[str, Any]], timeout_s: int = 300) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    endpoint = base_url.rstrip("/") + "/chat/agno"
    for item in questions:
        qid = str(item["id"])
        prompt = str(item["prompt"])
        t0 = time.perf_counter()
        response = requests.post(
            endpoint,
            json={"message": prompt, "use_knowledge": False, "session_id": f"agent-bench-{qid}"},
            timeout=timeout_s,
        )
        elapsed = round(time.perf_counter() - t0, 3)
        result: dict[str, Any] = {
            "id": qid,
            "category": item.get("category"),
            "question": prompt,
            "http_status": response.status_code,
            "elapsed_s": elapsed,
        }
        try:
            data = response.json()
        except Exception:  # noqa: BLE001 - 非 JSON 响应降级为 raw_text
            result["raw_text"] = response.text[:4000]
            results.append(result)
            continue
        result.update(_result_from_payload(qid=qid, prompt=prompt, elapsed=elapsed, data=data, http_status=response.status_code))
        results.append(result)
    return results


def run_questions_local(*, questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repo_root = Path(__file__).resolve().parents[2]
    backend_root = repo_root / "backend"
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))
    from services import agno_chat_service
    from storage.pg_pool import reset_pg_pool_for_tests

    results: list[dict[str, Any]] = []
    agno_chat_service.clear_agno_session_history_for_tests()
    reset_pg_pool_for_tests()
    for item in questions:
        qid = str(item["id"])
        prompt = str(item["prompt"])
        # Keep local benchmark runs isolated from prior pool state so route checks
        # are not polluted by stale or exhausted test connections.
        reset_pg_pool_for_tests()
        t0 = time.perf_counter()
        try:
            data = agno_chat_service.run_agno_chat_turn(
                prompt,
                session_id=f"agent-bench-{qid}",
                use_knowledge=False,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = round(time.perf_counter() - t0, 3)
            results.append(
                {
                    "id": qid,
                    "category": item.get("category"),
                    "question": prompt,
                    "http_status": 500,
                    "elapsed_s": elapsed,
                    "raw_text": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        elapsed = round(time.perf_counter() - t0, 3)
        result = {
            "id": qid,
            "category": item.get("category"),
            "question": prompt,
        }
        result.update(_result_from_payload(qid=qid, prompt=prompt, elapsed=elapsed, data=data, http_status=200))
        results.append(result)
    reset_pg_pool_for_tests()
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run agent eval benchmark against /chat/agno.")
    parser.add_argument(
        "--questions",
        default=str(Path(__file__).resolve().parents[2] / "benchmarks" / "agent_eval" / "questions_v1.json"),
    )
    parser.add_argument("--runner", choices=("local", "http"), default="local")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--output", default=str(Path(__file__).resolve().parents[2] / "_local" / "agent_eval_results.latest.json"))
    parser.add_argument("--timeout", type=int, default=300)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    question_doc = load_questions(Path(args.questions))
    if args.runner == "http":
        results = run_questions_http(
            base_url=args.base_url,
            questions=list(question_doc["questions"]),
            timeout_s=args.timeout,
        )
    else:
        results = run_questions_local(
            questions=list(question_doc["questions"]),
        )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
