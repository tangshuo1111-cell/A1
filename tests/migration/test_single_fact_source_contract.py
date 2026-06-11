"""Static contract — final exit fields only written in turn_exit_gate (pending resolver exempt)."""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
CHAT_ROOT = BACKEND_ROOT / "application" / "chat"

FINAL_WRITE_WHITELIST = {
    CHAT_ROOT / "turn_exit_gate.py",
    CHAT_ROOT / "turn_response_builder.py",
    CHAT_ROOT / "field_owners.py",
    CHAT_ROOT / "response_builders" / "field_writer.py",
    CHAT_ROOT / "response_builders" / "exit_extra_builder.py",
}

_GUARDED = frozenset({"task_status", "pending_kind", "primary_path"})


def _is_whitelisted(path: Path) -> bool:
    return path.resolve() in {p.resolve() for p in FINAL_WRITE_WHITELIST}


def _subscript_key(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Subscript):
        return None
    if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        return node.slice.value
    return None


def _subscript_base_name(node: ast.Subscript) -> str | None:
    if isinstance(node.value, ast.Name):
        return node.value.id
    return None


def _assign_target_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    return []


class _ExitWriteVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[str] = []
        self._skip_dict_depth = 0

    def visit_Call(self, node: ast.Call) -> None:
        func_name = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        if func_name == "build_common_exit_extra":
            self._skip_dict_depth += 1
            self.generic_visit(node)
            self._skip_dict_depth -= 1
            return
        if func_name == "apply_turn_exit_to_chat_turn":
            self._skip_dict_depth += 1
            self.generic_visit(node)
            self._skip_dict_depth -= 1
            return
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        targets = node.targets
        for target in targets:
            for name in _assign_target_names(target):
                if name in _GUARDED:
                    continue
            if isinstance(target, ast.Subscript):
                key = _subscript_key(target)
                base = _subscript_base_name(target)
                if key in _GUARDED and base == "extra":
                    self.violations.append(
                        f"{self.path.relative_to(BACKEND_ROOT)}:{node.lineno} extra[{key!r}] assign"
                    )
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        if self._skip_dict_depth > 0:
            return
        for key_node in node.keys:
            if isinstance(key_node, ast.Constant) and key_node.value in _GUARDED:
                self.violations.append(
                    f"{self.path.relative_to(BACKEND_ROOT)}:{node.lineno} dict_literal {key_node.value}"
                )
        self.generic_visit(node)


def test_no_final_exit_writes_outside_gate() -> None:
    offenders: list[str] = []
    for py in CHAT_ROOT.rglob("*.py"):
        if py.name.startswith("_") or _is_whitelisted(py):
            continue
        if py.name == "pending_kind.py":
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        visitor = _ExitWriteVisitor(py)
        visitor.visit(tree)
        rel = str(py.relative_to(CHAT_ROOT))
        for v in visitor.violations:
            if rel == "complex_pending_mapping.py":
                continue
            offenders.append(v)
    assert not offenders, "Unexpected extra[] exit writes:\n" + "\n".join(sorted(offenders)[:40])
