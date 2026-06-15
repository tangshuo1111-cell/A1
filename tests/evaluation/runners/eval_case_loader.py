from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tests.evaluation.runners.eval_assertions import (
    assert_expected_exists,
    assert_judge_exists,
    assert_required_fields,
    assert_unique_case_ids,
)

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_case_file() -> Path:
    return _repo_root() / "tests" / "evaluation" / "cases" / "v0_smoke.yaml"


def _load_yaml(path: Path) -> Any:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"evaluation case file not found: {path}") from exc
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError(f"failed to parse YAML case file '{path}': {exc}") from exc


def load_eval_cases(path: str | Path | None = None) -> list[dict[str, Any]]:
    case_path = Path(path) if path is not None else default_case_file()
    payload = _load_yaml(case_path)
    if not isinstance(payload, list):
        raise ValueError(f"evaluation case file must contain a top-level list: {case_path}")

    cases: list[dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"case #{index} in '{case_path}' must be an object/dict")
        case = dict(item)
        assert_required_fields(case)
        assert_expected_exists(case)
        assert_judge_exists(case)
        if "must_not_happen" not in case:
            case_id = str(case.get("case_id") or f"#{index}")
            raise ValueError(f"case '{case_id}' missing 'must_not_happen'")
        expected = case.get("expected") or {}
        if isinstance(expected, dict):
            expected.setdefault("warning_assertions", {})
        rule_ids = list(case.get("must_not_happen_rule_ids") or [])
        if not rule_ids:
            case_id = str(case.get("case_id") or f"#{index}")
            raise ValueError(f"case '{case_id}' missing explicit 'must_not_happen_rule_ids'")
        case["must_not_happen_rule_ids"] = rule_ids
        cases.append(case)

    assert_unique_case_ids(cases)
    return cases
