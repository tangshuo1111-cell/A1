"""
从 PG turn_product_metrics 生成周报 JSON（可选 HTML）。

```powershell
$env:PYTHONPATH = "backend"
py -3.12 scripts/report_product_metrics.py --days 7 --html
```

产物：`_local/reports/metrics/weekly_<end-date>.json`、`.html`
人工块（变更/判断/下周）请编辑同目录 `weekly_*_notes.md` 或 HTML 内占位区。
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

OUT_DIR = REPO_ROOT / "_local" / "reports" / "metrics"

PARTIAL_BUCKET_LABELS = {
    "answer_only_gap": "可 answer_only 重生成（003 主因）",
    "misjudged_gate": "深度/结构门误判",
    "material_gap": "材料不足",
    "commit_misroute": "commit 误路由",
    "insufficiency_expected": "预期 insufficiency",
    "budget_limited": "预算耗尽",
    "other": "其他",
}


def render_complex_diagnostic_html(breakdown: dict[str, Any]) -> str:
    if not breakdown:
        return ""
    buckets = breakdown.get("partial_buckets") or {}
    if not buckets and not breakdown.get("would_answer_refine_ids"):
        return ""
    rows = ""
    for key, count in sorted(buckets.items()):
        label = PARTIAL_BUCKET_LABELS.get(key, key)
        rows += f"<li>{_esc(label)} — {count}</li>"
    flip = breakdown.get("would_answer_refine_ids") or []
    flip_line = ""
    if flip:
        flip_line = f"<p>shadow would_answer_refine: {_esc(', '.join(str(x) for x in flip))}</p>"
    return (
        f"<h2>Complex partial 分解（诊断层）</h2>"
        f"<p>complex_total={breakdown.get('complex_total', 0)}, "
        f"complex_partial={breakdown.get('complex_partial', 0)}</p>"
        f"<ul>{rows or '<li>（无 partial 桶）</li>'}</ul>"
        f"{flip_line}"
    )


FAILURE_LABELS = {
    "insufficiency": "材料/证据不足",
    "external_capability_fail": "外部能力失败",
    "timeout_partial": "超时转 partial",
    "quality_gate_block": "质量门阻断",
    "upgrade_still_partial": "升级后仍 partial",
    "partial_other": "其他 partial",
    "failed_other": "其他失败",
}


def _period_bounds(days: int, end: datetime | None = None) -> tuple[tuple[str, str], tuple[str, str]]:
    end = end or datetime.now(UTC)
    cur_start = end - timedelta(days=days)
    prev_end = cur_start
    prev_start = prev_end - timedelta(days=days)
    def fmt(dt):
        return dt.isoformat()
    return (fmt(cur_start), fmt(end)), (fmt(prev_start), fmt(prev_end))


def _esc(text: str) -> str:
    return html.escape(str(text or ""), quote=True)


def _status_line(row: dict[str, Any]) -> str:
    status = str(row.get("task_status") or "—")
    code = str(row.get("failure_reason_code") or "")
    if code and code not in {"success", "other", ""}:
        label = FAILURE_LABELS.get(code, code)
        return f"{status} · {label}"
    return status


def _appendix_summary(row: dict[str, Any]) -> str:
    final = str(row.get("async_final_answer") or "").strip()
    base = str(row.get("answer_summary") or "—").strip() or "—"
    poll_st = str(row.get("async_poll_status") or "").strip().lower()
    poll_err = str(row.get("async_poll_error") or "").strip()

    if final:
        tag = poll_st or "done"
        return f"[后台终答·{tag}] {final}"
    if poll_st in {"failed", "expired", "cancelled"}:
        detail = poll_err or "网页动态抓取失败或超时，未生成总结正文"
        return f"⚠️ [后台失败·{poll_st}] {detail}"
    if poll_st in {"partial", "succeeded"}:
        return f"[后台·{poll_st}] {base}"
    if poll_st:
        return f"[后台·{poll_st}] {base}"
    return base


def _format_question_html(msg: str) -> str:
    text = (msg or "—").strip() or "—"
    idx = text.find("http://")
    if idx < 0:
        idx = text.find("https://")
    if idx > 0:
        head = _esc(text[:idx].strip())
        url = _esc(text[idx:].strip())
        return f'{head}<br/><span class="url">{url}</span>'
    return _esc(text)


def _appendix_timing(row: dict[str, Any]) -> str:
    sync_ms = row.get("timing_total_ms")
    bg_ms = row.get("async_background_ms")
    parts: list[str] = []
    if isinstance(sync_ms, (int, float)) and sync_ms >= 0:
        parts.append(f"首响 {sync_ms / 1000:.2f}s")
    if isinstance(bg_ms, (int, float)) and bg_ms > 0:
        parts.append(f"后台 {bg_ms / 1000:.2f}s")
    if parts:
        return " / ".join(parts)
    if isinstance(sync_ms, (int, float)):
        return f"{sync_ms / 1000:.2f} 秒"
    return "—"


def render_sample_appendix(raw_rows: list[dict[str, Any]]) -> str:
    if not raw_rows:
        return (
            "<p>（本周期无逐条样本记录；请确认 metrics 写入时已带 user_message，"
            "或重新跑沙箱样本后再生成周报。）</p>"
        )
    body = ""
    for idx, row in enumerate(raw_rows, 1):
        label = row.get("sample_label") or f"#{idx}"
        msg = row.get("message_text") or "—"
        summary = _appendix_summary(row)
        timing = _appendix_timing(row)
        poll_st = str(row.get("async_poll_status") or "").strip()
        async_col = _esc(poll_st) if poll_st else "—"
        body += (
            f'<tr>'
            f'<td class="col-id">{_esc(label)}</td>'
            f'<td class="col-question">{_format_question_html(str(msg))}</td>'
            f'<td class="col-status">{_esc(_status_line(row))}</td>'
            f'<td class="col-poll">{async_col}</td>'
            f'<td class="col-summary">{_esc(summary)}</td>'
            f'<td class="col-timing">{_esc(timing)}</td>'
            f"</tr>"
        )
    return f"""<div class="appendix-wrap">
<table class="appendix">
<colgroup>
  <col class="col-id" />
  <col class="col-question" />
  <col class="col-status" />
  <col class="col-poll" />
  <col class="col-summary" />
  <col class="col-timing" />
</colgroup>
<thead><tr><th>样本 ID</th><th>问题</th><th>首响状态</th><th>后台 poll</th><th>回答 / 后台终答</th><th>耗时</th></tr></thead>
<tbody>
{body}
</tbody>
</table>
</div>"""


def render_html(report: dict[str, Any]) -> str:
    cur = report["current"]
    prev = report["previous"]
    delta = report["delta"]

    def pct(v: float | None) -> str:
        if v is None:
            return "—"
        return f"{v * 100:.0f}%"

    def num(v: float | None, *, suffix: str = "") -> str:
        if v is None:
            return "—"
        if isinstance(v, float):
            return f"{v:.2f}{suffix}"
        return f"{v}{suffix}"

    def sec_from_ms(v: float | None) -> str:
        if v is None:
            return "—"
        return f"{v / 1000:.2f} 秒"

    def row(
        label: str,
        key: str,
        *,
        as_pct: bool = False,
        as_sec: bool = False,
    ) -> str:
        a = cur.get(key)
        b = prev.get(key)
        d = delta.get(key)
        if as_sec:
            av = sec_from_ms(a)
            bv = sec_from_ms(b)
            dv = "" if d is None else f"{d / 1000:+.2f} 秒"
        elif as_pct:
            av = pct(a)
            bv = pct(b)
            dv = "" if d is None else f"{d:+.2%}" if abs(d) < 2 else f"{d:+.2f}"
        else:
            av = num(a)
            bv = num(b)
            dv = "" if d is None else f"{d:+.2f}"
        return f"<tr><td>{label}</td><td>{av}</td><td>{bv}</td><td>{dv}</td></tr>"

    top3_lines = ""
    for item in cur.get("failure_top3") or []:
        code = item.get("code", "")
        label = FAILURE_LABELS.get(code, code)
        share = item.get("share_of_failures", 0) * 100
        top3_lines += f"<li>{label} — {share:.0f}%（占全部失败 turn 的比例）</li>"

    n_total = int(cur.get("turns_total") or 0)
    n_eval = int(cur.get("eval_item_count") or n_total)
    n_complex = int(cur.get("complex_task_count") or 0)
    n_async = int(cur.get("async_task_count") or 0)
    n_warn = (
        "<strong>解读约束</strong>：本周期为离线代表题（非全量线上请求）；"
        f"N={n_total}（N&lt;30），下列比率与 Δ 仅作趋势参考，不可外推。"
        if n_total < 30
        else ""
    )
    sample_block = (
        f'<div class="sample-n"><strong>【样本 N={n_total}】</strong>'
        f"离线 eval 代表题 {n_eval} 条；其中复杂子集 n={n_complex}，async 子集 n={n_async}。"
        f" {n_warn}</div>"
    )

    def _target_pct(v: float | None) -> str:
        return "—" if v is None else f"{v * 100:.0f}%"

    verdicts = report.get("target_verdicts") or []
    verdict_rows = ""
    for v in verdicts:
        prefix = "北极星 · " if v.get("is_north_star") else "Guardrail · "
        dir_sym = "≥" if v.get("direction") == "min" else "≤"
        status = str(v.get("status") or "")
        status_cls = {
            "达标": "v-pass",
            "未达标": "v-fail",
            "样本不足": "v-insufficient",
            "不适用（FAKE）": "v-insufficient",
        }.get(status, "")
        verdict_rows += (
            f"<tr>"
            f"<td>{_esc(prefix + str(v.get('label') or ''))}</td>"
            f"<td>{_target_pct(v.get('value'))}</td>"
            f"<td>目标 {dir_sym} {_target_pct(v.get('target'))}</td>"
            f"<td>N={int(v.get('sample_n') or 0)} / 下限 {int(v.get('min_sample') or 0)}</td>"
            f'<td class="{status_cls}"><strong>{_esc(status)}</strong></td>'
            f"</tr>"
        )
    verdict_block = (
        f'<div class="verdict">'
        f"<strong>【达标判定】</strong>观测口径，非线上 SLO 门禁；"
        f"样本量低于下限时标「样本不足」，只看趋势、不下达标结论。"
        f"<table><thead><tr><th>指标</th><th>本周值</th><th>目标线</th>"
        f"<th>样本量</th><th>判定</th></tr></thead><tbody>{verdict_rows}</tbody></table>"
        f"</div>"
        if verdict_rows
        else ""
    )

    env_banner = (
        '<div class="verdict" style="background:#fff4f4;border-color:#f0caca">'
        "<strong>【环境：FAKE LLM】</strong>本周报由 FAKE LLM 生成（占位回答），"
        "北极星2（复杂任务有效完成率）仅反映管线连通，<strong>不下达标结论</strong>"
        "（KI-METRICS-001）。真实达标趋势须用真实 LLM（LIGHT_MAQA_FAKE_LLM=0）复跑。</div>"
        if str(report.get("environment") or "REAL") == "FAKE"
        else ""
    )
    notes_path = report.get("notes_template_path", "")
    appendix_html = render_sample_appendix(report.get("sample_appendix") or [])
    diagnostic_html = render_complex_diagnostic_html(report.get("complex_failure_breakdown") or {})
    metric_guide = """
<div class="guide">
<strong>指标速览（先看这里）</strong>
<ul>
<li><strong>样本 N</strong>：必须先看清总请求数 N 与子集 n，再读任何百分比；N 过小（如 N&lt;30）时比率不可外推。</li>
<li><strong>样本</strong>：本周纳入统计的请求次数；「复杂 / async（异步）」是其中的子集计数。</li>
<li><strong>北极星 · 资料二次调用率</strong>：有检索发生的 turn 里，命中用户已 commit 资料的比例；分母为「有检索 chunk 的 turn」。</li>
<li><strong>北极星 · 复杂任务有效完成率</strong>：复杂题里，真正「答完 + 证据够 + 质量门（quality_gate）通过」的比例。<strong>partial（部分交付）不算完成</strong>。</li>
<li><strong>Guardrail（护栏）· Partial（部分交付）率</strong>：只交付了一部分、需要用户补材料或重试的比例；越高体验风险越大。</li>
<li><strong>Guardrail · 复杂升级率</strong>：本应从 fast（快路径）升级到 complex（复杂路径）或 agent 的比例；反映「题难但初判偏轻」的情况。</li>
<li><strong>Guardrail · 平均材料数</strong>：每次请求平均用到的检索块 + 临时材料数；纯文本直答、未开知识库时常为 0。</li>
<li><strong>Guardrail · insufficiency（证据不足）占比</strong>：因材料/证据不够被标记的 turn 占比；对应「答了但依据不足」。</li>
<li><strong>运行 · 平均总耗时 / P95（第 95 百分位）耗时</strong>：整轮请求 wall-clock 时间，单位<strong>秒</strong>。P95 表示约 95% 的请求不超过该耗时（尾部延迟观察）。</li>
<li><strong>质量 · quality_gate（质量门）通过率</strong>：规则质量门判定「可交付」的比例；未通过常见原因见下方失败 Top3。</li>
<li><strong>失败 Top3</strong>：失败/ partial 类 turn 中，最常见的 <code>failure_reason_code</code>（失败原因码）前三名。</li>
</ul>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<title>A1 产品协作周报</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:min(1200px,96vw);margin:2rem auto;padding:0 1rem;color:#1a1a1a;line-height:1.5}}
h1{{font-size:1.25rem}} h2{{font-size:1rem;margin-top:1.25rem}}
table{{border-collapse:collapse;width:100%;font-size:0.9rem}}
th,td{{border:1px solid #ddd;padding:0.5rem 0.65rem;text-align:left;vertical-align:top}}
.guide{{background:#fffbeb;border:1px solid #f0e6c8;padding:0.75rem 1rem;border-radius:6px;margin:1rem 0;font-size:0.88rem}}
.guide ul{{margin:0.5rem 0 0;padding-left:1.2rem}}
.guide li{{margin:0.35rem 0}}
.sample-n{{background:#eef6ff;border:1px solid #c5ddf5;padding:0.75rem 1rem;border-radius:6px;margin:1rem 0;font-size:0.92rem;line-height:1.55}}
.verdict{{background:#f4faf4;border:1px solid #cfe6cf;padding:0.75rem 1rem;border-radius:6px;margin:1rem 0;font-size:0.9rem}}
.verdict table{{margin-top:0.5rem}}
.verdict .v-pass{{color:#1a7f37;font-weight:600}}
.verdict .v-fail{{color:#b35900;font-weight:600}}
.verdict .v-insufficient{{color:#666;font-weight:600}}
.summary{{background:#f5f7fa;padding:0.75rem;border-radius:6px;margin:1rem 0}}
.footer{{font-size:0.75rem;color:#666;margin-top:2rem}}
code{{font-size:0.85em;background:#f0f0f0;padding:0.1em 0.3em;border-radius:3px}}
.appendix-wrap{{overflow-x:auto;margin:0.5rem 0 1rem;-webkit-overflow-scrolling:touch}}
table.appendix{{min-width:920px;table-layout:fixed;width:100%}}
table.appendix .col-id{{width:6rem;white-space:nowrap}}
table.appendix .col-status{{width:7.5rem;white-space:nowrap}}
table.appendix .col-poll{{width:5.5rem;white-space:nowrap}}
table.appendix .col-timing{{width:9.5rem;white-space:nowrap}}
table.appendix .col-question{{width:22%;word-break:normal;overflow-wrap:anywhere;line-height:1.45}}
table.appendix .col-summary{{width:auto;word-break:normal;overflow-wrap:anywhere;line-height:1.45}}
table.appendix .url{{font-size:0.82em;color:#444;word-break:break-all}}
table.appendix th{{background:#f8f9fb;font-weight:600}}
</style></head><body>
<h1>A1 产品协作周报</h1>
<p>周期：{report.get("period_current","")} vs {report.get("period_previous","")}</p>
{env_banner}
{sample_block}
{verdict_block}
{metric_guide}
<div class="summary"><strong>【结论】</strong>（请编辑 notes 或本段）有效完成率与 partial（部分交付）见下表；详见失败 Top3。</div>
<table>
<tr><th>指标</th><th>本周</th><th>上周</th><th>Δ</th></tr>
{row("【北极星】复杂任务有效完成率","complex_effective_complete_rate", as_pct=True)}
{row("【Guardrail（护栏）】Partial（部分交付）率","partial_rate", as_pct=True)}
{row("【Guardrail（护栏）】复杂升级率","complex_upgrade_rate", as_pct=True)}
{row("【Guardrail（护栏）】平均材料数","avg_material_count")}
{row("【Guardrail（护栏）】insufficiency（证据不足）占比","insufficiency_rate", as_pct=True)}
{row("【运行】平均总耗时（秒）","avg_timing_total_ms", as_sec=True)}
{row("【运行】P95（第95百分位）耗时（秒）","p95_timing_total_ms", as_sec=True)}
{row("【质量】quality_gate（质量门）通过率","quality_gate_pass_rate", as_pct=True)}
</table>
<h2>失败 Top3（failure_reason_code · 失败原因码）</h2>
<ul>{top3_lines or "<li>（无失败样本）</li>"}</ul>
{diagnostic_html}
<h2>逐条样本附录（问题 + 状态 + 摘要）</h2>
{appendix_html}
<h2>本周变化与下周动作</h2>
<p>【变更】请填写 — 模板：{notes_path}</p>
<p>【判断】请填写</p>
<p>【下周】请填写</p>
<p class="footer">说明：partial（部分交付）不计入有效完成；eval 为离线代表题（N={n_total}），非全量线上请求；以上为代理指标，非用户调研。本页耗时均由毫秒换算为秒展示。</p>
</body></html>"""


def main() -> None:
    from application.analytics.product_metrics import (
        aggregate_turn_rows,
        compare_periods,
        evaluate_targets,
        row_from_pg,
    )
    from storage.pg_pool import get_pool
    from storage.turn_product_metrics_pg import fetch_metrics_between

    parser = argparse.ArgumentParser(description="Product metrics weekly report")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--html", action="store_true")
    args = parser.parse_args()

    get_pool()
    (cur_start, cur_end), (prev_start, prev_end) = _period_bounds(args.days)

    cur_pg_rows = fetch_metrics_between(cur_start, cur_end)
    prev_pg_rows = fetch_metrics_between(prev_start, prev_end)
    cur_rows = [row_from_pg(r) for r in cur_pg_rows]
    prev_rows = [row_from_pg(r) for r in prev_pg_rows]

    report = compare_periods(aggregate_turn_rows(cur_rows), aggregate_turn_rows(prev_rows))
    # L13 观测层注入：FAKE LLM 运行时只标注、不改业务质量门 / 指标真源。
    fake_llm = (
        str(os.environ.get("LIGHT_MAQA_FAKE_LLM", "")).strip().lower()
        in {"1", "true", "yes", "on"}
    )
    report["environment"] = "FAKE" if fake_llm else "REAL"
    verdicts = evaluate_targets(report["current"])
    if fake_llm:
        # KI-METRICS-001：FAKE 下 complex 回答为占位文本 → 北极星2 不可外推；
        # 仅在报告层把该项判定改为「不适用（FAKE）」，不输出达标 / 未达标结论。
        for v in verdicts:
            if v.get("key") == "complex_effective_complete_rate":
                v["status"] = "不适用（FAKE）"
                v["environment_note"] = (
                    "FAKE LLM：仅验管线连通，不下达标结论（KI-METRICS-001）"
                )
    report["target_verdicts"] = verdicts
    report["period_current"] = f"{cur_start[:10]} – {cur_end[:10]}"
    report["period_previous"] = f"{prev_start[:10]} – {prev_end[:10]}"
    report["generated_at"] = datetime.now(UTC).isoformat()
    report["eval_scope"] = "offline_representative"
    report["sample_appendix"] = [
        {
            "sample_label": r.get("sample_label"),
            "message_text": r.get("message_text"),
            "task_status": r.get("task_status"),
            "failure_reason_code": r.get("failure_reason_code"),
            "answer_summary": r.get("answer_summary"),
            "timing_total_ms": r.get("timing_total_ms"),
            "is_complex_task": r.get("is_complex_task"),
            "async_final_answer": r.get("async_final_answer"),
            "async_poll_status": r.get("async_poll_status"),
            "async_background_ms": r.get("async_background_ms"),
        }
        for r in cur_pg_rows
    ]
    diag_path = OUT_DIR / "last_sandbox_diagnostic.json"
    if diag_path.is_file():
        try:
            diag_payload = json.loads(diag_path.read_text(encoding="utf-8"))
            report["complex_failure_breakdown"] = diag_payload.get("breakdown") or {}
        except (json.JSONDecodeError, OSError):
            report["complex_failure_breakdown"] = {}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    end_tag = cur_end[:10]
    json_path = OUT_DIR / f"weekly_{end_tag}.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {json_path}")

    notes_path = OUT_DIR / f"weekly_{end_tag}_notes.md"
    if not notes_path.exists():
        notes_path.write_text(
            "# 周报叙事（人工）\n\n【变更】\n\n【判断】\n\n【下周】\n",
            encoding="utf-8",
        )
    report["notes_template_path"] = str(notes_path.relative_to(REPO_ROOT))

    if args.html:
        html_path = OUT_DIR / f"weekly_{end_tag}.html"
        html_path.write_text(render_html(report), encoding="utf-8")
        print(f"wrote {html_path}")


if __name__ == "__main__":
    main()
