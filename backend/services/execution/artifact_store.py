"""Local artifact store for probe-phase reuse (§5.5)."""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from config.settings import settings

_ARTIFACT_ROOT = settings.data_dir.parent / "artifacts"


def _normalize_root(root: Path | None = None) -> Path:
    base = root or _ARTIFACT_ROOT
    base.mkdir(parents=True, exist_ok=True)
    return base


def _parse_ref(ref: str) -> tuple[str, str] | None:
    text = (ref or "").strip()
    if not text.startswith("local://sha256/"):
        return None
    body = text.removeprefix("local://sha256/")
    digest, _, query = body.partition("?")
    kind = "binary"
    if "kind=" in query:
        for part in query.split("&"):
            if part.startswith("kind="):
                kind = part.split("=", 1)[1] or kind
                break
    if len(digest) != 64:
        return None
    return digest, kind


def _artifact_path(digest: str, *, root: Path | None = None) -> Path:
    base = _normalize_root(root)
    return base / digest[:2] / digest


def put(content: bytes, *, kind: str, ttl_sec: int = 1800, root: Path | None = None) -> str:
    """Persist bytes and return artifact_ref."""
    digest = hashlib.sha256(content).hexdigest()
    target = _artifact_path(digest, root=root)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_bytes(content)
    os.replace(tmp, target)
    expires_at = int(time.time()) + max(1, int(ttl_sec))
    sidecar = target.with_suffix(".meta")
    sidecar.write_text(f"kind={kind}\nexpires_at={expires_at}\n", encoding="utf-8")
    return f"local://sha256/{digest}?kind={kind}&ttl={ttl_sec}"


def stat(ref: str, *, root: Path | None = None) -> dict[str, str | int] | None:
    parsed = _parse_ref(ref)
    if parsed is None:
        return None
    digest, kind = parsed
    path = _artifact_path(digest, root=root)
    if not path.is_file():
        return None
    meta: dict[str, str | int] = {"kind": kind, "size": path.stat().st_size}
    sidecar = path.with_suffix(".meta")
    if sidecar.is_file():
        for line in sidecar.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                meta[key.strip()] = value.strip()
    return meta


def get(ref: str, *, root: Path | None = None) -> bytes | None:
    parsed = _parse_ref(ref)
    if parsed is None:
        return None
    digest, _kind = parsed
    path = _artifact_path(digest, root=root)
    if not path.is_file():
        return None
    sidecar = path.with_suffix(".meta")
    if sidecar.is_file():
        expires_at = 0
        for line in sidecar.read_text(encoding="utf-8").splitlines():
            if line.startswith("expires_at="):
                try:
                    expires_at = int(line.split("=", 1)[1])
                except ValueError:
                    expires_at = 0
                break
        if expires_at and time.time() > expires_at:
            path.unlink(missing_ok=True)
            sidecar.unlink(missing_ok=True)
            return None
    return path.read_bytes()


def resolve_artifact_reuse(ref: str | None, *, root: Path | None = None) -> dict[str, bool | str | None]:
    """Return artifact.reused + artifact.miss_reason per §5.5.1."""
    if not (ref or "").strip():
        return {"artifact.reused": False, "artifact.miss_reason": None}
    parsed = _parse_ref(ref)
    if parsed is None:
        return {"artifact.reused": False, "artifact.miss_reason": "not_found"}
    digest, _kind = parsed
    path = _artifact_path(digest, root=root)
    sidecar = path.with_suffix(".meta")
    if sidecar.is_file():
        expires_at = 0
        for line in sidecar.read_text(encoding="utf-8").splitlines():
            if line.startswith("expires_at="):
                try:
                    expires_at = int(line.split("=", 1)[1])
                except ValueError:
                    expires_at = 0
                break
        if expires_at and time.time() > expires_at:
            return {"artifact.reused": False, "artifact.miss_reason": "expired"}
    if get(ref, root=root) is not None:
        return {"artifact.reused": True, "artifact.miss_reason": None}
    if not path.is_file() and not sidecar.is_file():
        return {"artifact.reused": False, "artifact.miss_reason": "not_found"}
    return {"artifact.reused": False, "artifact.miss_reason": "unavailable"}


def gc(*, root: Path | None = None) -> int:
    """Remove expired artifacts; return count removed."""
    base = _normalize_root(root)
    removed = 0
    now = time.time()
    for sidecar in base.rglob("*.meta"):
        expires_at = 0
        for line in sidecar.read_text(encoding="utf-8").splitlines():
            if line.startswith("expires_at="):
                try:
                    expires_at = int(line.split("=", 1)[1])
                except ValueError:
                    expires_at = 0
                break
        if expires_at and now > expires_at:
            artifact = sidecar.with_suffix("")
            artifact.unlink(missing_ok=True)
            sidecar.unlink(missing_ok=True)
            removed += 1
    return removed
