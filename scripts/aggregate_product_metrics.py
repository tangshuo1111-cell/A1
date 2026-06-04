"""
聚合产品指标 v1 — 从 JSONL 或 stdin（开发/debug）。

当前字段口径见 docs/pm/04_产品指标看板.md §7。
周报主路径请用 scripts/report_product_metrics.py（读 PG）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from application.analytics.product_metrics import aggregate_turn_rows  # noqa: E402


def main() -> None:
    rows = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    stats = aggregate_turn_rows(rows)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
