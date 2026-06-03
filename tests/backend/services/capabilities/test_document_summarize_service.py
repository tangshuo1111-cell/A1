from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.capabilities.document import summarize_service


def test_document_structured_summary_uses_higher_output_budget() -> None:
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="1. 要点一\n2. 要点二\n3. 要点三"))]

    with patch("openai.OpenAI") as openai_cls:
        client = MagicMock()
        client.chat.completions.create.return_value = fake_response
        openai_cls.return_value = client

        text = summarize_service.summarize_document(
            message="把这个文档总结成3-5个要点，告诉我它主要包含哪些 API 网址和用途。",
            material="文档正文" * 100,
        )

    call_kwargs = client.chat.completions.create.call_args.kwargs
    assert call_kwargs["max_tokens"] == 720
    assert "3-5 个要点" in call_kwargs["messages"][0]["content"]
    assert text.startswith("1. 要点一")


def test_document_plain_summary_keeps_small_budget() -> None:
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="简短回答"))]

    with patch("openai.OpenAI") as openai_cls:
        client = MagicMock()
        client.chat.completions.create.return_value = fake_response
        openai_cls.return_value = client

        text = summarize_service.summarize_document(
            message="这份文档主要讲什么？",
            material="文档正文" * 50,
        )

    call_kwargs = client.chat.completions.create.call_args.kwargs
    assert call_kwargs["max_tokens"] == 180
    assert "最短可用答案" in call_kwargs["messages"][0]["content"]
    assert text == "简短回答"


def test_document_default_summary_prefers_structured_points() -> None:
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="1. 要点一\n2. 要点二\n3. 要点三"))]

    with patch("openai.OpenAI") as openai_cls:
        client = MagicMock()
        client.chat.completions.create.return_value = fake_response
        openai_cls.return_value = client

        text = summarize_service.summarize_document(
            message="这个文档讲了什么？",
            material="文档正文" * 120,
        )

    call_kwargs = client.chat.completions.create.call_args.kwargs
    assert call_kwargs["max_tokens"] == 720
    assert "3-5 个要点" in call_kwargs["messages"][0]["content"]
    assert text.startswith("1. 要点一")


def test_document_summary_uses_extended_timeout() -> None:
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="简短回答"))]

    with patch("openai.OpenAI") as openai_cls:
        client = MagicMock()
        client.chat.completions.create.return_value = fake_response
        openai_cls.return_value = client

        summarize_service.summarize_document(
            message="这份文档主要讲什么？",
            material="文档正文" * 50,
        )

    openai_cls.assert_called_once()
    assert openai_cls.call_args.kwargs["timeout"] == 35.0
