from __future__ import annotations

from pathlib import Path


SANDBOX_SUBDIRS = (
    "uploads",
    "task_results",
    "kb_seed",
    "reports",
    "traces",
    "tmp",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def get_eval_sandbox_root() -> Path:
    return _repo_root() / "runtime_data" / "eval_sandbox"


def ensure_eval_sandbox_dirs() -> dict[str, Path]:
    root = get_eval_sandbox_root()
    root.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {"root": root}
    for name in SANDBOX_SUBDIRS:
        path = root / name
        path.mkdir(parents=True, exist_ok=True)
        paths[name] = path
    return paths


def clear_eval_sandbox_outputs() -> None:
    ensure_eval_sandbox_dirs()
    for path in list_eval_sandbox_dirs().values():
        if path.name == "eval_sandbox":
            continue
        for child in path.iterdir():
            if child.name in {"README.md", ".gitkeep"}:
                continue
            if child.is_dir():
                for nested in child.rglob("*"):
                    if nested.is_file():
                        nested.unlink()
                for nested_dir in sorted((p for p in child.rglob("*") if p.is_dir()), reverse=True):
                    nested_dir.rmdir()
                child.rmdir()
            else:
                child.unlink()


def list_eval_sandbox_dirs() -> dict[str, Path]:
    root = get_eval_sandbox_root()
    return {"root": root, **{name: root / name for name in SANDBOX_SUBDIRS}}
