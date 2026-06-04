"""EMBEDDING_ENABLED 为 commit 写向量与检索语义的唯一开关。"""
from __future__ import annotations

import pytest


def test_embed_on_commit_follows_embedding_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from config import settings as settings_mod
    from config.feature_flags import embed_on_commit_active

    monkeypatch.setattr(settings_mod.settings, "embedding_enabled", True)
    assert embed_on_commit_active() is True

    monkeypatch.setattr(settings_mod.settings, "embedding_enabled", False)
    assert embed_on_commit_active() is False


def test_feature_flags_no_embed_on_commit_flag() -> None:
    from config.feature_flags import FEATURE_FLAGS

    assert "ENABLE_EMBED_ON_COMMIT" not in FEATURE_FLAGS
