"""Video path / URL explicit signals (no agent-layer imports)."""

from __future__ import annotations

_PATH_STOP_CHARS = frozenset(
    " \t\r\n\u3000"
    "\"'`"
    "<>|"
    ",;!?"
    "\uff0c\uff1b\u3002\u3001\uff01\uff1f"
    "\uff1a"
)


def extract_mp4_path_from_message(message: str) -> str | None:
    msg = (message or "").strip()
    if not msg:
        return None
    msg_lower = msg.lower()
    if ".mp4" not in msg_lower:
        return None
    candidates: list[str] = []
    pos = 0
    while True:
        idx = msg_lower.find(".mp4", pos)
        if idx < 0:
            break
        end = idx + 4
        start = idx
        while start > 0 and msg[start - 1] not in _PATH_STOP_CHARS:
            start -= 1
        path = msg[start:end].strip()
        if path and path.lower().endswith(".mp4"):
            candidates.append(path)
        pos = end
    if not candidates:
        return None
    candidates.sort(key=len, reverse=True)
    return candidates[0]
