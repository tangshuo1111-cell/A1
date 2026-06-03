"""证据归一化：失败文案 / MCP / RAG 头块不得进入用户证据列表。"""

from agents.evidence_normalizer import normalize_evidence_lists, sanitize_evidence_text
from rag.ingest import _fts_boost_header


def test_drop_rag_boost_header():
    header = _fts_boost_header("knowledge_samples/x.md", "# Title\n\nbody")
    ne, ns, tr = normalize_evidence_lists([header, "正文段落说明项目。"], ["rag", "rag"])
    assert len(ne) == 1
    assert "正文段落" in ne[0]
    assert any("rag_boost_header" in x for x in tr)


def test_drop_mcp_and_local_fail():
    ne, ns, tr = normalize_evidence_lists(
        ["[MCP·进程内模拟] {'ok': true}", "[本地文件·失败] x: nope", "可用正文"],
        ["mcp_sim", "tool_file", "rag"],
    )
    assert len(ne) == 1
    assert ne[0] == "可用正文"
    assert any("mcp" in x for x in tr)
    assert any("local_file_failed" in x for x in tr)


def test_sanitize_tool_file_strips_prefix():
    t = sanitize_evidence_text("[本地文件] foo.md\nhello world", "tool_file")
    assert "[本地文件]" not in t
    assert "hello world" in t


def test_sanitize_tool_url_strips_prefix():
    t = sanitize_evidence_text("[url] https://a.com\nsnippet", "tool_url")
    assert "snippet" in t
    assert "https" not in t
