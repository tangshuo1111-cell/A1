"""
网页 HTML 正文抽取（tools / fetch 子层）。

优先 BeautifulSoup 去噪；失败则退化为空白折叠。
供 tools.tools.fetch_url 与 HTTP 工具复用，不向 LangGraph 直接暴露。
"""

from __future__ import annotations


def extract_readable_text(html: str, max_chars: int = 8000) -> str:
    if not html:
        return ""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
    except (ImportError, ValueError, TypeError):
        text = html
    compact = " ".join(text.split())
    return compact[:max_chars]
