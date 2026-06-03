from rag.result_cleaner import demote_boost_preserve_order, sort_hits_body_before_boost


def test_body_before_boost():
    rows = [
        {"text": "[doc_path] a [doc_file] b [doc_title] t [demo_keywords] x"},
        {"text": "这是正文 chunk。"},
    ]
    out = sort_hits_body_before_boost(rows)
    assert "正文" in out[0]["text"]


def test_demote_after_rank():
    ranked = [
        {"text": "[doc_path] a [doc_file] b [doc_title] t [demo_keywords] x"},
        {"text": "second body"},
        {"text": "[doc_path] c [doc_file] d [doc_title] u [demo_keywords] y"},
    ]
    slim = demote_boost_preserve_order(ranked, top_k=3)
    assert slim[0]["text"].startswith("second")
