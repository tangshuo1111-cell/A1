"""
上传限制规则。

定义文件上传的大小、类型、后缀白名单。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config.cost_rule import COST


@dataclass(frozen=True)
class UploadLimit:
    """上传安全限制。"""

    max_size_mb: int = field(default_factory=lambda: COST.upload_max_mb)

    allowed_extensions: tuple[str, ...] = (
        ".pdf", ".docx", ".xlsx", ".txt", ".md",
        ".png", ".jpg", ".jpeg", ".gif", ".webp",
        ".mp3", ".wav", ".mp4", ".webm",
    )

    allowed_mime_prefixes: tuple[str, ...] = (
        "application/pdf",
        "application/vnd.openxmlformats",
        "text/",
        "image/",
        "audio/",
        "video/",
    )

    # 拒绝的后缀（可执行文件等）
    blocked_extensions: tuple[str, ...] = (
        ".exe", ".bat", ".cmd", ".ps1", ".sh",
        ".dll", ".so", ".dylib",
        ".js", ".py", ".rb", ".php",
    )

    @property
    def max_size_bytes(self) -> int:
        return self.max_size_mb * 1024 * 1024

    def is_allowed(self, filename: str, size_bytes: int, mime: str = "") -> tuple[bool, str]:
        """检查文件是否允许上传，返回 (allowed, reason)。"""
        if size_bytes > self.max_size_bytes:
            return False, f"文件过大：{size_bytes} bytes > {self.max_size_mb} MB"

        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        if ext in self.blocked_extensions:
            return False, f"禁止上传的文件类型：{ext}"

        if self.allowed_extensions and ext not in self.allowed_extensions:
            return False, f"不支持的文件类型：{ext}"

        if mime and not any(mime.startswith(p) for p in self.allowed_mime_prefixes):
            return False, f"不支持的 MIME 类型：{mime}"

        return True, ""


UPLOAD = UploadLimit()
