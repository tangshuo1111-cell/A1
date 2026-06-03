from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
from utf8_console import configure_utf8_stdio  # noqa: E402 - sys.path 注入后才能导入

configure_utf8_stdio()


def load_json(path: Path) -> dict[str, Any] | list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _item_score(item: dict[str, Any]) -> float:
    return float(item.get("score") or 0.0)


def _classify_judgment(item: dict[str, Any]) -> str:
    routing = item.get("routing") or {}
    path = routing.get("primary_path")
    http_status = int(routing.get("http_status") or 0)
    if http_status >= 500:
        return "后端错误"
    if _item_score(item) < 1:
        return "严重异常"
    if path == "agno_basic":
        return "Agent 主链样本"
    if path == "direct_llm":
        return "fast 直答样本"
    return "其他"


def render_report(*, benchmark_id: str, scored: dict[str, Any], output_path: Path) -> str:
    summary = scored.get("summary") or {}
    items = scored.get("items") or []
    lines: list[str] = []
    lines.append(f"# Agent 评测基准报告：{benchmark_id}")
    lines.append("")
    lines.append("## 1. 总览")
    lines.append("")
    lines.append(f"- benchmark_id: `{benchmark_id}`")
    lines.append(f"- 平均分（全部）: `{summary.get('average_score_all', 'n/a')}`")
    lines.append(f"- 平均分（去掉重大失败）: `{summary.get('average_score_without_major_failures', 'n/a')}`")
    lines.append(f"- 重大失败题目: `{', '.join(summary.get('major_failure_ids', [])) or '无'}`")
    lines.append(f"- Agent 代表题: `{', '.join(summary.get('best_agent_cases', [])) or '无'}`")
    lines.append(f"- 结论: {summary.get('conclusion', '')}")
    lines.append("")
    lines.append("## 2. 路由与质量总表")
    lines.append("")
    lines.append("| 题目 | 路径 | 模式 | HTTP | 耗时(s) | 分数 | 类型 |")
    lines.append("|---|---|---:|---:|---:|---:|---|")
    for item in items:
        routing = item.get("routing") or {}
        lines.append(
            f"| {item.get('id')} | `{routing.get('primary_path')}` | `{routing.get('mode')}` | "
            f"{routing.get('http_status')} | {routing.get('elapsed_s')} | {_item_score(item):.1f} | {_classify_judgment(item)} |"
        )
    lines.append("")
    lines.append("## 3. 单题摘要")
    lines.append("")
    for item in items:
        routing = item.get("routing") or {}
        scores = item.get("dimension_scores") or {}
        lines.append(f"### {item.get('id')}")
        lines.append("")
        lines.append(f"- 路径: `{routing.get('primary_path')}`")
        lines.append(f"- 模式: `{routing.get('mode')}`")
        lines.append(f"- HTTP: `{routing.get('http_status')}`")
        lines.append(f"- 耗时: `{routing.get('elapsed_s')}s`")
        lines.append(f"- 总分: `{_item_score(item):.1f}`")
        lines.append("- 维度分:")
        lines.append(f"  - structure: `{scores.get('structure')}`")
        lines.append(f"  - reasoning_depth: `{scores.get('reasoning_depth')}`")
        lines.append(f"  - multi_view: `{scores.get('multi_view')}`")
        lines.append(f"  - evidence_sense: `{scores.get('evidence_sense')}`")
        lines.append(f"  - prudence: `{scores.get('prudence')}`")
        lines.append(f"  - actionability: `{scores.get('actionability')}`")
        lines.append(f"- 判断: {item.get('judgment', '')}")
        lines.append("")
    lines.append("## 4. 架构备注")
    lines.append("")
    lines.append("- 这套 benchmark 的目的，是测复杂推理组织能力与复杂题路由质量。")
    lines.append("- 多 Agent 主链不应该依赖后台 task join 才成立；它更适合消费 fast 专项能力链、知识入库结果和 RAG 检索材料，再做复杂分析。")
    lines.append("- 因此后续复跑时，既要看答案质量，也要看复杂题是否稳定进入 Agent 主链。")
    text = "\n".join(lines) + "\n"
    output_path.write_text(text, encoding="utf-8")
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a Markdown benchmark report from scored agent eval JSON.")
    parser.add_argument("--benchmark-id", required=True)
    parser.add_argument("--scored-json", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    scored = load_json(Path(args.scored_json))
    if not isinstance(scored, dict):
        raise SystemExit("scored-json must be an object payload")
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    render_report(benchmark_id=args.benchmark_id, scored=scored, output_path=out)
    print(out)


if __name__ == "__main__":
    main()
