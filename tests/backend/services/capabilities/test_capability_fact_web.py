"""S6 — web capability contract when ENABLE_CAPABILITY_FACT_WEB is on."""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from application.chat.budget_clock import BudgetClock
from config import feature_flags
from services.capabilities.web import web_orchestration_service
from services.capabilities.web.static_body_extract import minimal_html_to_plain_text


@pytest.fixture
def enable_capability_fact_web(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_CAPABILITY_FACT_WEB", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_DECISION_ARBITRATOR", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_BUDGET_CLOCK_V2", True)


def test_probe_web_capability_marks_dynamic_required_for_spa_shell() -> None:
    html = (
        "<html><head><title>App</title></head><body>"
        '<div id="root"></div><script>window.__NEXT_DATA__={}</script>'
        "</body></html>"
    )
    with patch.object(web_orchestration_service, "_http_get_text", return_value=html):
        fact, advice = web_orchestration_service.probe_web_capability("https://spa.example.com/app")
    assert fact.dynamic_required is True
    assert fact.lane == "web"
    assert advice.suggested_mode == "demote_to_async"
    assert advice.reason == "dynamic_content_required"


def test_probe_web_capability_static_fetch_ok() -> None:
    html = (
        "<html><head><title>Article</title></head><body>"
        "<article>" + ("这是可静态抓取的网页正文。" * 40) + "</article>"
        "</body></html>"
    )
    with patch.object(web_orchestration_service, "_http_get_text", return_value=html):
        fact, advice = web_orchestration_service.probe_web_capability("https://example.com/article")
    assert fact.dynamic_required is False
    assert fact.cookie_required is False
    assert fact.quality_level == "good"
    assert advice.suggested_mode == "sync_ok"
    assert fact.metadata.get("static_fetch_ok") is True


def test_minimal_html_to_plain_text_prefers_article_and_drops_navigation_noise() -> None:
    # 正文需足够长以走主路径（容器评分选 <article>）；过短会触发 trafilatura
    # 回退拿原始 html 重抽、把 <nav> 噪声带回，且其行为随 trafilatura 版本漂移。
    para1 = "第一段正文。" + "这是文章的核心论述内容，用于说明正文优先与导航噪声剔除。" * 3
    para2 = "第二段正文。" + "这里继续展开第二个要点，确保正文长度超过质量阈值。" * 3
    html = f"""
    <html><body>
      <header>无障碍链接</header>
      <nav>主页 中国 国际 Facebook Twitter</nav>
      <article>
        <h1>正文标题</h1>
        <p>{para1}</p>
        <p>{para2}</p>
      </article>
      <footer>Print Options</footer>
    </body></html>
    """
    text = minimal_html_to_plain_text(html)
    assert "正文标题" in text
    assert "第一段正文" in text
    assert "第二段正文" in text
    assert "无障碍链接" not in text
    assert "Facebook" not in text
    assert "Print Options" not in text


def test_minimal_html_to_plain_text_trims_related_section_at_tail() -> None:
    body = "这是正文段落。" * 80
    html = f"""
    <html><body>
      <article>
        <h1>文章标题</h1>
        <p>{body}</p>
        <h2>相关文章</h2>
        <p>另一篇推荐文章标题</p>
        <p>第三篇推荐文章标题</p>
      </article>
    </body></html>
    """
    text = minimal_html_to_plain_text(html)
    assert "文章标题" in text
    assert "这是正文段落" in text
    assert "相关文章" not in text
    assert "另一篇推荐文章标题" not in text


def test_minimal_html_to_plain_text_does_not_trim_tail_marker_in_short_body() -> None:
    html = """
    <html><body>
      <article>
        <p>短正文。</p>
        <p>相关内容</p>
        <p>后续补充说明。</p>
      </article>
    </body></html>
    """
    text = minimal_html_to_plain_text(html)
    assert "短正文" in text
    assert "相关内容" in text
    assert "后续补充说明" in text


def test_minimal_html_to_plain_text_drops_ad_blocks_inside_article() -> None:
    html = """
    <html><body>
      <article>
        <p>""" + ("正文内容。" * 60) + """</p>
        <div class="advertisement">广告位</div>
        <p>""" + ("正文续篇。" * 60) + """</p>
      </article>
    </body></html>
    """
    text = minimal_html_to_plain_text(html)
    assert "正文内容" in text
    assert "正文续篇" in text
    assert "广告位" not in text


def test_minimal_html_to_plain_text_dedupes_news_header_and_tail_echo() -> None:
    body = "美国国务院星期一表示，将对中国系统性打压美国新闻报道的行为予以坚决反制。" * 12
    title = "美中互相驱逐对方一名记者后，美国誓言反制北京压制美国媒体"
    html = f"""
    <html><body>
      <article>
        <div class="breadcrumb">美中关系</div>
        <h1>{title}</h1>
        <span class="author">林枫</span>
        <time>2026年6月2日 05:32</time>
        <h1>{title}</h1>
        <p>{body}</p>
        <div class="author-block">
          <p>{title}</p>
          <p>林枫</p>
          <p>美国之音记者</p>
        </div>
      </article>
    </body></html>
    """
    text = minimal_html_to_plain_text(html)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines[0] == title
    assert "美中关系" not in text
    assert "美国之音记者" not in text
    assert text.count(title) == 1
    assert "美国国务院星期一表示" in text


def test_minimal_html_to_plain_text_filters_ads_photo_credits_and_merges_fragments() -> None:
    body = (
        "台湾总统赖清德的发言人谴责北京对《纽约时报》记者的驱逐行动，"
        "北京此举是对赖清德去年12月通过视频连线参加《纽约时报》DealBook峰会一事的回应。"
        "与此同时，中国试图孤立台湾。"
    ) * 8
    html = f"""
    <html><body>
      <article>
        <p class="byline">DAVID PIERSON</p>
        <time>2026年6月1日</time>
        <figure>
          <figcaption>上个月，赖清德在台北。</figcaption>
          <span class="image-credit">Chiang Ying-Ying/Associated Press</span>
        </figure>
        <p>{body}</p>
        <p>这位驻北京记者王月眉(Vivian Wang)<span>于</span><span>2月被驱逐</span>。</p>
        <div class="ad-slot">广告</div>
        <p>王月眉自2020年起担任《纽约时报》驻华记者。</p>
      </article>
    </body></html>
    """
    text = minimal_html_to_plain_text(html)
    assert "DAVID PIERSON" in text
    assert "2026年6月1日" in text
    assert "台湾总统赖清德的发言人谴责" in text
    assert "王月眉(Vivian Wang)于2月被驱逐" in text
    assert "广告" not in text
    assert "Associated Press" not in text
    assert "上个月，赖清德在台北" not in text


def test_minimal_html_to_plain_text_doc_site_picks_content_and_trims_toc() -> None:
    intro = (
        "以往，开发团队使用 Postman、Swagger 等多种工具来管理 API 文档，"
        "接口调试与 Mock 数据往往分散在不同平台，协作成本较高。"
        "Apifox 将 API 文档、调试、Mock、自动化测试集成到同一工作台。"
    ) * 3
    html = f"""
    <html><body>
      <main>
        <aside class="docs-sidebar">
          <a href="/start">开始使用</a>
          <a href="/intro">产品介绍</a>
          <a href="/download">下载 Apifox</a>
          <a href="/quick">快速入门</a>
          <a href="/faq">常见问题</a>
        </aside>
        <div class="doc-content">
          <h1>Apifox 帮助文档</h1>
          <div class="menu-inline">开始使用 产品介绍 下载 Apifox 快速入门 常见问题 Apifox 官网</div>
          <h2>产品介绍</h2>
          <p>{intro}</p>
        </div>
      </main>
    </body></html>
    """
    text = minimal_html_to_plain_text(html)
    assert "产品介绍" in text
    assert "以往，开发团队使用 Postman" in text
    assert "开始使用" not in text
    assert "快速入门" not in text
    assert "Apifox 官网" not in text


def test_normalize_extracted_lines_merges_orphan_numbered_list_rows() -> None:
    from services.capabilities.web.static_body_extract import normalize_extracted_lines

    lines = [
        "这种工作流程带来了三个核心优势：1.",
        "促进了团队各角色间的紧密协作。",
        "2.",
        "实现了有组织的 API 管理。",
    ]
    out = normalize_extracted_lines(lines)
    merged = "\n".join(out)
    assert "优势：1.促进了团队" in merged
    assert "2.实现了有组织的 API 管理" in merged
    assert merged.count("\n2.\n") == 0


def test_normalize_extracted_lines_drops_markdown_only_heading_lines() -> None:
    from services.capabilities.web.static_body_extract import normalize_extracted_lines

    lines = ["产品介绍", "#", "##", "这是正文段落，包含足够长度。"]
    out = normalize_extracted_lines(lines)
    assert all(ln.strip() not in {"#", "##"} for ln in out)
    assert "这是正文段落" in "\n".join(out)


def test_minimal_html_to_plain_text_trims_share_pdf_tail_on_long_doc() -> None:
    body = "这是文档正文段落。" * 80
    html = f"""
    <html><body>
      <article>
        <p>{body}</p>
        <p>向他人分享 Apifox#下载 PDF以下是Apifox</p>
        <p>功能介绍 PDF 文件，欢迎您将它分享至团队内部或向他人推荐。</p>
      </article>
    </body></html>
    """
    text = minimal_html_to_plain_text(html)
    assert "这是文档正文段落" in text
    assert "向他人分享" not in text
    assert "下载 PDF" not in text
    assert "功能介绍 PDF" not in text


def test_pick_content_container_prefers_article_body_over_wrapper_with_nav() -> None:
    from bs4 import BeautifulSoup

    from services.capabilities.web.static_body_extract import pick_content_container

    html = """
    <html><body>
      <main>
        <nav><a>首页</a><a>文档</a><a>博客</a><a>下载</a></nav>
        <article class="article-content">
          <p>""" + ("这是独立正文区域。" * 40) + """</p>
        </article>
      </main>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    node = pick_content_container(soup)
    assert node is not None
    assert "article-content" in " ".join(node.get("class") or [])


def test_minimal_html_to_plain_text_trafilatura_fallback_when_primary_poor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html = """
    <html><body>
      <main>
        <div class="sidebar">目录项一 目录项二 目录项三 目录项四 目录项五</div>
        <div class="sidebar">目录项六 目录项七 目录项八 目录项九 目录项十</div>
      </main>
    </body></html>
    """
    fallback_body = "这是 trafilatura 回退得到的完整正文。" * 30

    def fake_trafilatura(raw_html: str, page_url: str) -> str:
        assert raw_html
        return fallback_body

    monkeypatch.setattr(
        "tools.web.common.extract_with_trafilatura",
        fake_trafilatura,
    )
    text = minimal_html_to_plain_text(html, url="https://docs.example.com/page")
    assert "trafilatura 回退得到的完整正文" in text
    assert "目录项一" not in text


def test_probe_web_capability_cookie_required_on_403() -> None:
    response = httpx.Response(403, request=httpx.Request("GET", "https://private.example.com"))
    with patch.object(
        web_orchestration_service,
        "_http_get_text",
        side_effect=httpx.HTTPStatusError("403", request=response.request, response=response),
    ):
        fact, advice = web_orchestration_service.probe_web_capability("https://private.example.com")
    assert fact.cookie_required is True
    assert advice.suggested_mode == "demote_to_async"
    assert advice.reason == "cookie_required"


def test_fetch_web_fast_material_prefers_direct_page_body_for_explicit_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html = (
        "<html><body><article>"
        + ("这是网页正文内容。" * 160)
        + "</article></body></html>"
    )
    monkeypatch.setattr(web_orchestration_service, "_http_get_text", lambda _url: html)
    monkeypatch.setattr(
        web_orchestration_service,
        "fetch_web_evidence_block",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("direct body should win")),
    )
    material = web_orchestration_service.fetch_web_fast_material(
        "https://example.com/article 这个网页讲了什么",
        max_results=2,
    )
    assert material.startswith("[网页正文]")
    assert "https://example.com/article" in material
    assert "这是网页正文内容" in material


def test_run_web_fast_path_demotes_when_dynamic_required(
    enable_capability_fact_web,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from application.chat import fast_path_entry
    from services.capabilities.contracts import CapabilityAdvice, CapabilityFact

    fact = CapabilityFact(
        lane="web",
        probe_elapsed_ms=50,
        dynamic_required=True,
        cookie_required=False,
        quality_level="poor",
    )
    advice = CapabilityAdvice(
        suggested_mode="demote_to_async",
        reason="dynamic_content_required",
    )
    monkeypatch.setattr(web_orchestration_service, "probe_web_capability", lambda url, clock=None: (fact, advice))
    monkeypatch.setattr(
        web_orchestration_service,
        "fetch_web_evidence_block",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("fetch must not run")),
    )

    out = fast_path_entry.run_web_fast_path(
        message="请总结 https://spa.example.com/page",
        context_block=None,
        clock=BudgetClock.start(),
    )
    assert out is not None
    answer, extra = out
    assert "后台" in answer
    assert extra["capabilities_called"] == ["capability.web.probe"]
    assert extra["arbitrator.decided_mode"] == "async"
    assert extra["capability_advice"].suggested_mode == "demote_to_async"


def test_run_web_fast_path_uses_direct_material_helper(
    enable_capability_fact_web,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from application.chat import fast_path_entry
    from services.capabilities.contracts import CapabilityAdvice, CapabilityFact

    fact = CapabilityFact(
        lane="web",
        probe_elapsed_ms=20,
        dynamic_required=False,
        cookie_required=False,
        quality_level="good",
        metadata={"url": "https://example.com/article"},
    )
    advice = CapabilityAdvice(
        suggested_mode="sync_ok",
        reason="static_fetch_ok",
    )
    monkeypatch.setattr(web_orchestration_service, "probe_web_capability", lambda url, clock=None: (fact, advice))
    monkeypatch.setattr(
        web_orchestration_service,
        "fetch_web_fast_material",
        lambda *_a, **_k: "[网页正文] example.com\nURL: https://example.com/article\n正文:\n真实网页正文",
    )

    out = fast_path_entry.run_web_fast_path(
        message="https://example.com/article 这个网页讲了什么",
        context_block=None,
        clock=BudgetClock.start(),
    )
    assert out is not None
    answer, extra = out
    assert answer
    assert extra["fast_exit_reason"] == "web_static_fetch_answer"
    assert extra["capabilities_called"] == ["capability.web.static_fetch"]
    assert extra["web_primary_source"] == "page_body"
    assert extra["web_supplement_source"] == "none"


def test_run_web_fast_path_returns_fulltext_when_requested(
    enable_capability_fact_web,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from application.chat import fast_path_entry
    from services.capabilities.contracts import CapabilityAdvice, CapabilityFact

    fact = CapabilityFact(
        lane="web",
        probe_elapsed_ms=20,
        dynamic_required=False,
        cookie_required=False,
        quality_level="good",
        metadata={"url": "https://example.com/article"},
    )
    advice = CapabilityAdvice(
        suggested_mode="sync_ok",
        reason="static_fetch_ok",
    )
    monkeypatch.setattr(web_orchestration_service, "probe_web_capability", lambda url, clock=None: (fact, advice))
    monkeypatch.setattr(
        web_orchestration_service,
        "fetch_web_fast_material",
        lambda *_a, **_k: "[网页正文] example.com\nURL: https://example.com/article\n正文:\n第一段\n第二段",
    )

    out = fast_path_entry.run_web_fast_path(
        message="https://example.com/article 把整个网页的全文提取出来给我",
        context_block=None,
        clock=BudgetClock.start(),
    )
    assert out is not None
    answer, extra = out
    assert answer == "第一段\n第二段"
    assert extra["web_output_mode"] == "fulltext"
    assert extra["fast_exit_reason"] == "web_static_fetch_fulltext"


def test_enqueue_web_passes_prefilled_fact(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.capabilities.contracts import CapabilityFact
    from services.execution import task_plane_service

    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_ASYNC_CONTROL_PLANE_V2", True)
    created: list[dict] = []
    monkeypatch.setattr(
        "services.execution.task_plane_service.task_job_store.create_task",
        lambda task_id, **kwargs: created.append({"task_id": task_id, **kwargs}) or None,
    )
    monkeypatch.setattr(
        "services.execution.task_plane_service.enqueue_async_task",
        lambda _msg: "memory",
    )
    monkeypatch.setattr(
        "services.execution.task_plane_service.ensure_async_workers_started",
        lambda: None,
    )
    monkeypatch.setattr(
        "services.execution.task_plane_service.task_job_store.update_task_async_metadata",
        lambda *a, **k: None,
    )
    fact = CapabilityFact(
        lane="web",
        probe_elapsed_ms=80,
        dynamic_required=True,
        cookie_required=False,
        quality_level="poor",
    )
    task_plane_service.enqueue_web_heavy_fetch_task(
        url="https://example.com/heavy",
        session_id="s6",
        prefilled_fact=fact,
    )
    assert created
    meta = created[0]["metadata"]
    assert meta["capability_dynamic_required"] is True
    assert meta["capability_probe_elapsed_ms"] == 80
