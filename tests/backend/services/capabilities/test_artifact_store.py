"""S4a — artifact_store put/get/stat/gc."""
from __future__ import annotations

from pathlib import Path

from services.execution import artifact_store


def test_artifact_store_put_get_roundtrip(tmp_path: Path):
    ref = artifact_store.put(b"audio-bytes", kind="audio", ttl_sec=1800, root=tmp_path)
    assert ref.startswith("local://sha256/")
    assert artifact_store.get(ref, root=tmp_path) == b"audio-bytes"
    stat = artifact_store.stat(ref, root=tmp_path)
    assert stat is not None
    assert stat["kind"] == "audio"


def test_artifact_store_expired_returns_none(tmp_path: Path):
    ref = artifact_store.put(b"expire-me", kind="audio", ttl_sec=1, root=tmp_path)
    sidecar = next(tmp_path.rglob("*.meta"))
    sidecar.write_text("kind=audio\nexpires_at=1\n", encoding="utf-8")
    assert artifact_store.get(ref, root=tmp_path) is None


def test_artifact_store_gc_removes_expired(tmp_path: Path):
    ref = artifact_store.put(b"gc-me", kind="audio", ttl_sec=1, root=tmp_path)
    sidecar = next(p for p in tmp_path.rglob("*.meta") if p.with_suffix("").name in ref)
    sidecar.write_text("kind=audio\nexpires_at=1\n", encoding="utf-8")
    removed = artifact_store.gc(root=tmp_path)
    assert removed >= 1
    assert artifact_store.get(ref, root=tmp_path) is None
