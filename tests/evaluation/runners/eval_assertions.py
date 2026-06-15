from __future__ import annotations

from typing import Any

from tests.evaluation.runners.eval_rule_catalog import (
    RULE_CHECKERS,
    build_observed_fields,
    classify_rule,
    classify_rule_id,
)


REQUIRED_FIELDS = (
    "case_id",
    "case_name",
    "category",
    "user_input",
    "expected",
    "judge",
    "must_not_happen",
    "must_not_happen_rule_ids",
)


def assert_required_fields(case: dict[str, Any]) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in case]
    if missing:
        case_id = str(case.get("case_id") or "<missing-case-id>")
        raise ValueError(f"case '{case_id}' missing required fields: {', '.join(missing)}")


def assert_expected_exists(case: dict[str, Any]) -> None:
    if "expected" not in case:
        case_id = str(case.get("case_id") or "<missing-case-id>")
        raise ValueError(f"case '{case_id}' missing 'expected'")


def assert_judge_exists(case: dict[str, Any]) -> None:
    if "judge" not in case:
        case_id = str(case.get("case_id") or "<missing-case-id>")
        raise ValueError(f"case '{case_id}' missing 'judge'")


def assert_unique_case_ids(cases: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for case in cases:
        case_id = str(case.get("case_id") or "")
        if case_id in seen:
            duplicates.append(case_id)
        seen.add(case_id)
    if duplicates:
        dup_text = ", ".join(sorted(set(duplicates)))
        raise ValueError(f"duplicate case_id found: {dup_text}")


def assert_allowed_value(actual: Any, allowed: list[Any] | tuple[Any, ...], field_name: str) -> None:
    if actual not in allowed:
        allowed_text = ", ".join(repr(item) for item in allowed)
        raise ValueError(f"{field_name}={actual!r} not in allowed values: {allowed_text}")


def assert_required_trace_fields(actual_extra: dict[str, Any] | None, required_fields: list[str]) -> None:
    extra = actual_extra or {}
    missing = [field for field in required_fields if field not in extra]
    if missing:
        raise ValueError(f"missing required trace fields: {', '.join(missing)}")


def check_must_not_happen_basic(
    result: dict[str, Any],
    must_not_happen: list[str],
    *,
    must_not_happen_rule_ids: list[str] | None = None,
) -> tuple[list[str], list[str], list[dict[str, str]]]:
    actual = result.get("actual") or {}
    observed = build_observed_fields(actual)
    normalized_rules = [str(rule).strip() for rule in must_not_happen if str(rule).strip()]
    hard_failures: list[str] = []
    warnings: list[str] = []
    matched_rules: list[dict[str, str]] = []
    resolved_rule_ids: list[tuple[str, str]] = []

    for rule_id in list(must_not_happen_rule_ids or []):
        meta = classify_rule_id(rule_id)
        matched_rules.append(
            {
                "rule_id": meta.rule_id,
                "level": meta.level,
                "enforcement": meta.enforcement,
                "source": "rule_id",
                "executed": "false",
                "outcome": "configured",
            }
        )
        resolved_rule_ids.append((meta.rule_id, "rule_id"))

    if not resolved_rule_ids:
        for rule in normalized_rules:
            meta = classify_rule(rule)
            matched_rules.append(
                {
                    "rule_id": meta.rule_id,
                    "level": meta.level,
                    "enforcement": meta.enforcement,
                    "source": "rule_text",
                    "executed": "false",
                    "outcome": "configured",
                }
            )
            resolved_rule_ids.append((meta.rule_id, "rule_text"))

    seen: set[tuple[str, str]] = set()
    for rule_id, source in resolved_rule_ids:
        if (rule_id, source) in seen:
            continue
        seen.add((rule_id, source))
        meta = classify_rule_id(rule_id)
        checker = RULE_CHECKERS.get(rule_id)
        for item in matched_rules:
            if item["rule_id"] == rule_id and item["source"] == source:
                item["executed"] = "true"
        if checker is None:
            message = f"{rule_id}: configured without checker"
            for item in matched_rules:
                if item["rule_id"] == rule_id and item["source"] == source:
                    item["outcome"] = "missing_checker"
            warnings.append(message)
            continue
        verdict = checker(observed)
        if not verdict.matched:
            for item in matched_rules:
                if item["rule_id"] == rule_id and item["source"] == source:
                    item["outcome"] = "executed_no_match"
            continue
        if verdict.enforcement == "hard_fail":
            for item in matched_rules:
                if item["rule_id"] == rule_id and item["source"] == source:
                    item["outcome"] = "matched_hard_fail"
            hard_failures.append(verdict.message or rule_id)
        else:
            for item in matched_rules:
                if item["rule_id"] == rule_id and item["source"] == source:
                    item["outcome"] = "matched_warning"
            warnings.append(verdict.message or rule_id)
    return hard_failures, warnings, matched_rules


def assert_must_not_happen_basic(result: dict[str, Any], must_not_happen: list[str]) -> None:
    hard_failures, _warnings, _matched = check_must_not_happen_basic(result, must_not_happen)
    if hard_failures:
        raise ValueError("; ".join(hard_failures))


def assert_task_status_is_canonical(task_status: str | None) -> None:
    canonical = ("pending", "succeeded", "failed", "blocked", "partial")
    if task_status not in canonical:
        raise ValueError(
            f"task_status={task_status!r} is not canonical; allowed: {', '.join(canonical)}"
        )
