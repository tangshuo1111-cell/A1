"""
视频 URL 链 cookies 文件的前端管理接口（协议层）。

为什么有这一组接口
------------------
yt-dlp 的 cookies 注入已实现：
- ``VIDEO_COOKIES_FROM_BROWSER`` 直接从浏览器 cookies 库读，最方便；
- 但 Win11 的 App-Bound Encryption / DPAPI 限制让本地浏览器路径**经常**失败
  （edge 报 DPAPI 解密失败、chrome 报 cookies 数据库被锁），实测两个主流
  浏览器都过不了 B 站；
- 唯一稳的路是手动导出 ``cookies.txt`` 文件 + ``VIDEO_COOKIES_FILE`` 配置。

但**让用户去改 .env + 重启后端**对非技术用户不友好。R3 把这条路完整搬到
前端：检测到视频链失败 → 弹"我来教你"卡片 → 用户上传 cookies.txt →
后端落到固定位置 + runtime **热更新** ``settings.video_cookies_file`` →
下一轮 yt-dlp 自动用上。

设计边界（与 R1/R2 严格一致）
----------------------------
- **不写 .env**：上传只更新 runtime ``settings.video_cookies_file`` 与本地文件，
  避免敏感 cookies 落到 git tracked 的 .env / 多用户共享 .env 等场景；
  进程重启后**默认清空**（除非用户在 .env 里手动配了）。
- **白名单 host 校验**：只接受 cookies.txt 里至少含**一个**白名单域名的 cookie
  （bilibili.com / youtube.com / tiktok.com 等，沿用 ``settings.video_url_domain_set``），
  防止误传 / 攻击者拿其他站 cookies。
- **大小上限**：1 MB（单个用户的浏览器 cookies 远小于此）。
- **格式校验**：必须是 Netscape HTTP Cookie File 头、或至少**一行**像 cookie
  （7 个 \\t 分割字段）—— 避免上传错文件。
- **失败显式**：任何校验失败都返回 4xx + 明确 error code + 中文 message，
  前端按 code 分支显示。
- **单文件（上传落盘）**：R3 只往 ``<data_dir>/cookies/video_cookies.txt`` 写一份；
  若该文件不存在，``Settings.video_cookies_choice()`` 还会自动尝试仓库内
  ``data/cookies/video_cookies.txt``（与样例对齐、免配 ``VIDEO_COOKIES_FILE``）。
  多账号场景未来扩展（按 session_id 隔离）属 R3 之外。

接口
----
- ``GET    /config/video_cookies/status`` —— 当前 cookies 状态（含哪些站、什么时候改的）
- ``POST   /config/video_cookies/upload`` —— multipart 上传 cookies.txt
- ``DELETE /config/video_cookies``        —— 清除（文件 + runtime 设置）

权限
----
- 与 ``/ingest`` 等 admin 路由一致，**ADMIN_API_KEY 非空时**才校验
  ``X-Admin-Key``；本地默认零摩擦。
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile
from fastapi import File as _File

from api.api_errors import raise_validation
from api.deps import verify_admin_optional
from api.schemas_http import (
    VideoCookiesDeleteResponse,
    VideoCookiesFileStatus,
    VideoCookiesMergeInfo,
    VideoCookiesStatusResponse,
    VideoCookiesUploadResponse,
)
from config.settings import settings

logger = logging.getLogger("light_maqa")
router = APIRouter()


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
_MAX_UPLOAD_BYTES = 1 * 1024 * 1024  # 1 MB；浏览器 cookies 远小于此
_COOKIES_FILENAME = "video_cookies.txt"
_COOKIES_SUBDIR = "cookies"


def _cookies_storage_path() -> Path:
    """统一的 cookies 文件落盘路径：``<data_dir>/cookies/video_cookies.txt``。

    ``data_dir`` 已在 ``settings.py`` 默认指向项目根的 ``data/``，
    与 sqlite db 同目录管理，不再额外引入新位置。
    """
    base = settings.data_dir / _COOKIES_SUBDIR
    base.mkdir(parents=True, exist_ok=True)
    return base / _COOKIES_FILENAME


# ---------------------------------------------------------------------------
# Netscape cookies.txt 解析（轻量、容错）
# ---------------------------------------------------------------------------
_NETSCAPE_HEADER_RE = re.compile(r"^\s*#\s*(Netscape\s+HTTP\s+Cookie\s+File|HTTP\s+Cookie\s+File)\b", re.IGNORECASE | re.MULTILINE)
# Netscape 行：domain\tHTTPONLY?\tpath\tsecure\texpires\tname\tvalue
# 第一列 domain；以 # 开头的是注释；空行跳过
_COOKIE_LINE_RE = re.compile(r"^([^\s#][^\t]*)\t.*\t.*\t.*\t.*\t.*\t.*$")


@dataclass(frozen=True)
class _ParsedCookies:
    domains: frozenset[str]
    line_count: int


def _parse_cookies_text(text: str) -> _ParsedCookies:
    """解析 Netscape cookies.txt：抽出所有 cookie 行的 domain 列。

    - 不做严格 RFC 校验，只做"看起来像 cookies.txt"判断；
    - 把首列 ``.bilibili.com`` 这类前缀点去掉，再 lowercase；
    - 不包含任何 cookie 行 → 空集（让上层判定"非法文件"）。
    """
    domains: set[str] = set()
    n = 0
    for raw in text.splitlines():
        line = raw.rstrip("\r\n")
        if not line or line.lstrip().startswith("#"):
            continue
        m = _COOKIE_LINE_RE.match(line)
        if not m:
            continue
        d = m.group(1).strip().lower().lstrip(".")
        if d:
            domains.add(d)
            n += 1
    return _ParsedCookies(domains=frozenset(domains), line_count=n)


def _matches_any_whitelist(host: str, whitelist: frozenset[str]) -> bool:
    """host 命中白名单（与 url_fetch._host_matches_whitelist 同款语义）：
    完全相等或为白名单条目的子域。"""
    h = (host or "").strip().lower()
    if not h:
        return False
    for entry in whitelist:  # noqa: SIM110
        if h == entry or h.endswith("." + entry):
            return True
    return False


# ---------------------------------------------------------------------------
# 状态读取
# ---------------------------------------------------------------------------
def _file_status(path: Path) -> dict:
    """读取本地 cookies 文件的元信息（不读 cookies 值，避免泄露）。"""
    if not path.exists() or not path.is_file():
        return {"exists": False, "size_bytes": 0, "modified_iso": None, "domains": [], "matched_whitelist_domains": []}
    try:
        st = path.stat()
        size = int(st.st_size)
        mtime_iso = datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat(timespec="seconds")
    except OSError:
        size = 0
        mtime_iso = None

    domains: list[str] = []
    matched: list[str] = []
    try:
        # 限制读取大小，避免有人把异常大文件丢进来
        text = path.read_text(encoding="utf-8", errors="ignore")[: _MAX_UPLOAD_BYTES + 1]
        parsed = _parse_cookies_text(text)
        domains = sorted(parsed.domains)
        wl = settings.video_url_domain_set()
        matched = sorted(d for d in parsed.domains if _matches_any_whitelist(d, wl))
    except OSError:
        pass

    return {
        "exists": True,
        "size_bytes": size,
        "modified_iso": mtime_iso,
        "domains": domains,
        "matched_whitelist_domains": matched,
    }


def _video_cookies_status_payload() -> VideoCookiesStatusResponse:
    """返回 cookies 当前状态，给前端 ``VideoCookiesGuide`` 组件渲染。

    返回字段（**全部稳定**，前端类型可对齐）：
    - ``source``: ``"browser:<name>"`` / ``"file"`` / ``"none"``
                  —— 即 ``settings.video_cookies_choice()`` 的结论
    - ``effective_path``: ``str | None`` —— 当前实际生效的文件路径（仅 source=file 时有）
    - ``managed_path``:   ``str``        —— 前端"上传"接口会写入的固定路径
    - ``managed_file``:   ``dict``       —— 上面这个文件的状态（exists/size/modified/domains）
    - ``whitelist_domains``: ``list[str]`` —— 当前白名单（前端展示"我可以为这些站上传"）
    - ``upload_max_bytes``: ``int``      —— 大小上限（前端预校验）
    """
    kind, value = settings.video_cookies_choice()
    if kind == "browser":
        source = f"browser:{value}"
    elif kind == "file":
        source = "file"
    else:
        source = "none"

    managed = _cookies_storage_path()
    file_status = _file_status(managed)
    return VideoCookiesStatusResponse(
        ok=True,
        source=source,
        effective_path=value if kind == "file" else None,
        managed_path=str(managed),
        managed_file=VideoCookiesFileStatus.model_validate(file_status),
        whitelist_domains=sorted(settings.video_url_domain_set()),
        upload_max_bytes=_MAX_UPLOAD_BYTES,
    )


@router.get("/video_cookies/status", dependencies=[Depends(verify_admin_optional)], response_model=VideoCookiesStatusResponse)
def video_cookies_status() -> VideoCookiesStatusResponse:
    return _video_cookies_status_payload()


# ---------------------------------------------------------------------------
# 上传
# ---------------------------------------------------------------------------
def _line_domain(line: str) -> str:
    """抽 Netscape cookie 行的首列 domain，统一去前缀点 + 小写；非 cookie 行返回 ""。"""
    m = _COOKIE_LINE_RE.match(line.rstrip("\r\n"))
    if not m:
        return ""
    return m.group(1).strip().lower().lstrip(".")


def _merge_cookies_by_domain(
    *, existing_text: str, new_text: str, new_domains: frozenset[str]
) -> tuple[str, list[str], list[str]]:
    """按 domain 合并新旧 cookies.txt。

    规则：
    - 新文件中出现的 domain → 完全用新行（包含所有该 domain 的 cookie）
    - 旧文件中独有的 domain → 原行原样保留
    - 注释行（# 开头）：新文件的注释**不保留**到合并产物（避免重复堆积），
      旧文件的注释行**也不保留**（合并产物只生成一份标准头）
    - 输出始终带 ``# Netscape HTTP Cookie File`` 头，方便 yt-dlp 识别

    返回 ``(merged_text, kept_old_domains, replaced_domains)``：
    - kept_old_domains：旧文件里被保留下来的 domain（用于前端展示"已保留 bilibili 等"）
    - replaced_domains：旧文件里被新文件覆盖的 domain（用于前端展示"刷新了 youtube"）
    """
    new_domains_norm = frozenset(d.lower().lstrip(".") for d in new_domains)

    kept_old_lines: list[str] = []
    kept_old_domains: set[str] = set()
    replaced_domains: set[str] = set()
    if existing_text:
        for raw in existing_text.splitlines():
            line = raw.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            d = _line_domain(line)
            if not d:
                continue
            if d in new_domains_norm:
                replaced_domains.add(d)
                continue
            kept_old_lines.append(line)
            kept_old_domains.add(d)

    new_lines: list[str] = []
    for raw in new_text.splitlines():
        line = raw.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not _line_domain(line):
            continue
        new_lines.append(line)

    parts: list[str] = ["# Netscape HTTP Cookie File"]
    if kept_old_lines:
        parts.append("# --- preserved from previous upload ---")
        parts.extend(kept_old_lines)
    if new_lines:
        parts.append("# --- this upload ---")
        parts.extend(new_lines)
    merged = "\n".join(parts) + "\n"
    return merged, sorted(kept_old_domains), sorted(replaced_domains)


def _validate_and_persist(content: bytes, *, filename_hint: str = "") -> VideoCookiesUploadResponse:
    """共享校验 + 落盘 + runtime 热更新逻辑，路由层只做协议适配。

    上传不再覆盖磁盘已有 cookies；按 domain 合并：
    - 新上传中出现的 domain → 用新行（刷新登录态）
    - 旧文件里独有的 domain → 保留（B 站 + 抖音 + YouTube 共存）
    """
    if not content:
        raise_validation("EMPTY_FILE", "上传内容为空，请确认你导出的 cookies.txt 不是空文件。")
    if len(content) > _MAX_UPLOAD_BYTES:
        raise_validation(
            "TOO_LARGE",
            f"文件超过 {_MAX_UPLOAD_BYTES // 1024} KB 上限。正常 cookies.txt 远小于这个值，"
            "请确认上传的不是错误文件。",
            http_status=413,
        )
    # errors="ignore" 下 bytes→str 不抛解码异常，无需 try/except
    text = content.decode("utf-8", errors="ignore")

    # 头部识别（不强求；某些扩展导出时不写头，所以只在缺头**且没任何 cookie 行**时才报错）
    has_header = bool(_NETSCAPE_HEADER_RE.search(text))
    parsed = _parse_cookies_text(text)
    if parsed.line_count == 0:
        raise_validation(
            "NOT_COOKIES_TXT",
            "文件不像 Netscape 格式的 cookies.txt：没有解析出任何 cookie 行。"
            f"{' 且文件首部缺少 # Netscape HTTP Cookie File 头。' if not has_header else ''}",
        )

    wl = settings.video_url_domain_set()
    matched = [d for d in parsed.domains if _matches_any_whitelist(d, wl)]
    if not matched:
        raise_validation(
            "NO_WHITELIST_DOMAIN",
            "上传的 cookies 里没有任何视频站点 cookie："
            f"已识别 {len(parsed.domains)} 个域，但都不在白名单里。"
            f"白名单：{', '.join(sorted(wl))}。"
            "请确认你导出的是 bilibili.com / youtube.com 等视频站的 cookies。",
        )

    # 合并而不是覆盖
    target = _cookies_storage_path()
    existing_text = ""
    if target.exists() and target.is_file():
        try:
            existing_text = target.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            existing_text = ""

    merged_text, kept_old_domains, replaced_domains = _merge_cookies_by_domain(
        existing_text=existing_text,
        new_text=text,
        new_domains=parsed.domains,
    )
    merged_bytes = merged_text.encode("utf-8")

    # 落盘：原子写入（先写 tmp 再 replace），避免半写状态被 yt-dlp 读到
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(merged_bytes)
    tmp.replace(target)

    # runtime 热更新：让下一轮 fetch_video_text 立即拿到新文件
    settings.video_cookies_file = str(target.resolve())  # type: ignore[misc]

    # 合并后磁盘的最终 domain 集合（前端展示"现在覆盖了哪些站"）
    final_parsed = _parse_cookies_text(merged_text)
    final_matched = sorted(d for d in final_parsed.domains if _matches_any_whitelist(d, wl))

    logger.info(
        "v11r5b cookies merged path=%s new_size=%d merged_size=%d "
        "new_domains=%s replaced=%s kept=%s final_matched=%s filename=%s",
        target,
        len(content),
        len(merged_bytes),
        ",".join(sorted(parsed.domains))[:120],
        ",".join(replaced_domains)[:120],
        ",".join(kept_old_domains)[:120],
        ",".join(final_matched)[:120],
        filename_hint,
    )

    return VideoCookiesUploadResponse(
        ok=True,
        managed_path=str(target),
        size_bytes=len(merged_bytes),
        matched_whitelist_domains=final_matched,
        all_domains=sorted(final_parsed.domains),
        hot_reloaded=True,
        merge=VideoCookiesMergeInfo(
            new_domains=sorted(parsed.domains),
            kept_old_domains=kept_old_domains,
            replaced_domains=replaced_domains,
        ),
    )


@router.post(
    "/video_cookies/upload",
    dependencies=[Depends(verify_admin_optional)],
    response_model=VideoCookiesUploadResponse,
)
async def upload_video_cookies(file: UploadFile = _File(...)) -> VideoCookiesUploadResponse:  # noqa: B008
    """multipart 上传 cookies.txt。

    成功返回：
        ``{"ok": True, "managed_path": "<abs>", "size_bytes": N,
           "matched_whitelist_domains": [...], "all_domains": [...], "hot_reloaded": True}``

    失败返回 4xx + ``{"detail": {"code": "<CODE>", "message": "<中文>"}}``，
    code 集合：``EMPTY_FILE / TOO_LARGE / DECODE_FAILED / NOT_COOKIES_TXT / NO_WHITELIST_DOMAIN``。
    """
    # FastAPI 已经做了基本类型校验；这里限制读取量
    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    return await asyncio.to_thread(
        _validate_and_persist, content, filename_hint=file.filename or ""
    )


# ---------------------------------------------------------------------------
# 清除
# ---------------------------------------------------------------------------
@router.delete(
    "/video_cookies",
    dependencies=[Depends(verify_admin_optional)],
    response_model=VideoCookiesDeleteResponse,
)
def delete_video_cookies() -> VideoCookiesDeleteResponse:
    """删除托管的 cookies 文件 + 把 runtime ``video_cookies_file`` 清空。

    幂等：文件不存在时也返回 ok=True，方便前端多次点"清除"不报错。
    注意：**不**碰 ``video_cookies_from_browser``（那是 .env 显式配的，
    用户清 cookies 文件不代表想关浏览器路径）。
    """
    target = _cookies_storage_path()
    removed = False
    if target.exists():
        try:
            target.unlink()
            removed = True
        except OSError as e:
            from core.errors import AppError, ErrorCategory
            raise AppError(
                code="DELETE_FAILED",
                message=f"删除失败：{e}",
                category=ErrorCategory.STORAGE,
            ) from e

    # 只清"我们 R3 托管的那一份"；如果 .env 显式配了别的 file 路径则不动
    managed_resolved = str(target.resolve())
    cur = (settings.video_cookies_file or "").strip()
    if cur and Path(cur).resolve() == Path(managed_resolved):
        settings.video_cookies_file = ""  # type: ignore[misc]

    logger.info("v11r3 cookies cleared removed=%s path=%s", removed, target)
    return VideoCookiesDeleteResponse(ok=True, removed=removed, managed_path=str(target))
