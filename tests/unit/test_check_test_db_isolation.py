from __future__ import annotations

from scripts.check_test_db_isolation import _line_has_prod_db


def test_prod_db_name_is_detected() -> None:
    assert _line_has_prod_db("DATABASE_URL=postgresql://u:p@127.0.0.1:5432/light_maqa") is True


def test_sandbox_db_name_is_allowed() -> None:
    assert (
        _line_has_prod_db(
            "DATABASE_URL=postgresql://u:p@127.0.0.1:5433/light_maqa_metrics_sandbox"
        )
        is False
    )


def test_ci_suffix_is_allowed() -> None:
    assert _line_has_prod_db("postgresql://u:p@127.0.0.1:5432/light_maqa_ci") is False
