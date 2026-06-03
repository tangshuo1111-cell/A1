"""Upload-facing bridge.

Upload accepts raw incoming material and hands it to the pending lifecycle.
"""

from knowledge.pending.service import (
    prepare_document_source,
    prepare_file_source,
    prepare_ocr_source,
    prepare_text_source,
    prepare_video_source,
    prepare_web_search_source,
    prepare_web_url_source,
)

__all__ = [
    "prepare_document_source",
    "prepare_file_source",
    "prepare_ocr_source",
    "prepare_text_source",
    "prepare_video_source",
    "prepare_web_search_source",
    "prepare_web_url_source",
]
