from __future__ import annotations

from tests.evaluation.runners.eval_case_loader import default_case_file, load_eval_cases
from tests.evaluation.runners.eval_sandbox import (
    clear_eval_sandbox_outputs,
    ensure_eval_sandbox_dirs,
    get_eval_sandbox_root,
)


def test_v0_smoke_case_file_exists() -> None:
    assert default_case_file().exists()


def test_loader_reads_cases() -> None:
    cases = load_eval_cases()
    assert len(cases) == 8


def test_case_ids_are_unique() -> None:
    cases = load_eval_cases()
    case_ids = [case["case_id"] for case in cases]
    assert len(case_ids) == len(set(case_ids))


def test_required_fields_exist_on_each_case() -> None:
    required = {"case_id", "case_name", "category", "user_input", "expected", "judge", "must_not_happen"}
    for case in load_eval_cases():
        assert required.issubset(case.keys())
        assert case["must_not_happen_rule_ids"]


def test_expected_field_exists() -> None:
    for case in load_eval_cases():
        assert "expected" in case


def test_judge_field_exists() -> None:
    for case in load_eval_cases():
        assert "judge" in case


def test_must_not_happen_exists() -> None:
    for case in load_eval_cases():
        assert "must_not_happen" in case


def test_eval_sandbox_dirs_can_be_created() -> None:
    paths = ensure_eval_sandbox_dirs()
    for path in paths.values():
        assert path.exists()
        assert path.is_dir()


def test_reset_does_not_delete_readme_or_gitkeep() -> None:
    ensure_eval_sandbox_dirs()
    root = get_eval_sandbox_root()
    readme = root / "README.md"
    if not readme.exists():
        readme.write_text("# eval sandbox\n", encoding="utf-8")
    uploads_keep = root / "uploads" / ".gitkeep"
    uploads_keep.touch(exist_ok=True)
    dummy = root / "tmp" / "dummy.txt"
    dummy.write_text("temp", encoding="utf-8")

    clear_eval_sandbox_outputs()

    assert readme.exists()
    assert uploads_keep.exists()
    assert not dummy.exists()
