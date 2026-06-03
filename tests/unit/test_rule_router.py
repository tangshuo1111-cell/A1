"""agents.main_agent.rule_router：decide() 规则基线多分支（无 LLM 精炼时 router_source=rules）。"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from tests._support.bootstrap import find_repo_root

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.main_agent.rule_router import decide  # noqa: E402
from schemas import TaskInput  # noqa: E402


def _task(q: str, **kwargs: object) -> TaskInput:
    return TaskInput(
        task_id="rt-1",
        user_query=q,
        clean_query=q,
        created_at=datetime.now(UTC),
        **kwargs,
    )


def test_trivial_greeting_direct_no_rag() -> None:
    d = decide(_task("你好"))
    assert d.answer_channel == "direct"
    assert d.need_rag is False
    assert d.router_source == "rules"


def test_knowledge_inventory_goes_kb() -> None:
    d = decide(_task("知识库里有什么主题或文件线索？"))
    assert d.need_rag is True
    assert d.answer_channel == "kb"


def test_realtime_web_external_channel() -> None:
    d = decide(_task("今天广州天气怎么样"))
    assert d.need_external_info is True
    assert d.answer_channel == "external"


def test_plain_url_message_external() -> None:
    d = decide(
        _task(
            "请看 https://example.com/page",
            has_link=True,
            link_urls=["https://example.com/page"],
        )
    )
    assert d.need_external_info is True
    assert d.answer_channel == "external"


def test_project_scoped_question_kb() -> None:
    d = decide(_task("本项目支持哪些能力？"))
    assert d.need_rag is True
    assert d.answer_channel == "kb"


def test_extended_smalltalk_direct() -> None:
    d = decide(_task("谢谢"))
    assert d.answer_channel == "direct"
    assert d.need_rag is False


def test_casual_social_direct() -> None:
    d = decide(_task("你今天心情怎么样"))
    assert d.answer_channel == "direct"
    assert d.need_rag is False


def test_general_world_knowledge_direct() -> None:
    d = decide(_task("易拉罐怎么开"))
    assert d.answer_channel == "direct"
    assert d.need_rag is False


def test_sample_path_under_knowledge_samples_kb_local_first() -> None:
    d = decide(_task("总结 knowledge_samples/md/sample_success.md 里写的要点"))
    assert d.need_rag is True
    assert d.need_tool_local is True
    assert d.middle_collect_priority == "local_first"


def test_long_generic_question_defaults_kb() -> None:
    q = "请系统性介绍 RAG 检索里向量库与倒排索引各适合什么场景，并对比优缺点。" * 2
    d = decide(_task(q))
    assert d.need_rag is True
    assert d.answer_channel == "kb"


def test_plain_one_char_or_empty_is_direct() -> None:
    """极短寒暄类：不进知识库。"""
    assert decide(_task("好")).answer_channel == "direct"
    assert decide(_task("ok")).answer_channel == "direct"


def test_list_files_need_local_tool() -> None:
    """「列出示例 / 列出知识库文件」触发本地只读工具。"""
    d = decide(_task("列出 knowledge_samples 下有哪些示例文件"))
    assert d.need_tool_local is True
    assert d.need_rag is True


def test_read_file_keywords_need_local_tool() -> None:
    d = decide(_task("请读取文件 knowledge_samples/md/sample_success.md"))
    assert d.need_tool_local is True


def test_search_and_today_hits_external_web_task() -> None:
    """显式检索词 + 「今天」等实时语境 → external。"""
    d = decide(_task("请上网搜索一下今天的科技新闻简报"))
    assert d.answer_channel == "external"
    assert d.need_external_info is True
    assert d.need_rag is False


def test_doc_readme_in_query_goes_kb() -> None:
    """提到 README / 文档 + 问询 → 文档语境，优先知识库（无链接也可用）。"""
    d = decide(_task("README 文档里对产品能力怎么描述的？"))
    assert d.answer_channel == "kb"
    assert d.need_rag is True


def test_steps_style_for_howto() -> None:
    """含「文档/README/项目」语境 + 教程/步骤用词 → KB + steps。"""
    d = decide(_task("README 的安装说明里，从零开始应该怎么操作？请按步骤列出"))
    assert d.answer_style == "steps"
    assert d.answer_channel == "kb"


def test_compare_style_when_vs_keyword() -> None:
    d = decide(_task("对比一下 Keyword 检索和向量检索在项目里怎么用 vs 场景"))
    assert d.answer_style == "compare"
    assert d.need_rag is True


def test_compound_marked_when_two_questions() -> None:
    d = decide(_task("什么是 RAG？以及怎么用它来回答用户问题？"))
    assert d.is_compound is True


def test_followup_with_snippet_need_context() -> None:
    d = decide(
        _task(
            "那前文说的第二点具体怎么做？",
            is_followup=True,
            context_snippet="（摘要）用户之前问过部署步骤……",
        )
    )
    assert d.need_context is True


def test_greeting_and_link_stays_external_priority() -> None:
    """寒暄 + URL：仍可走外链抓取，不靠 RAG 冒充网页。"""
    d = decide(
        _task(
            "你好，看下这个页面 https://news.example.org/a",
            has_link=True,
            link_urls=["https://news.example.org/a"],
        )
    )
    assert d.answer_channel == "external"
    assert d.need_external_info is True
    assert d.need_rag is False


def test_explain_style_for_definition_question() -> None:
    """通识定义型：在无项目锚点时走 direct，且常为 explain。"""
    d = decide(_task("激光是什么"))
    assert d.answer_channel == "direct"
    assert d.answer_style == "explain"
