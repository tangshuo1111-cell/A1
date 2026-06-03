"""Video tools package.

Keep package init light to avoid circular imports during service-layer bootstrap.
Submodules should be imported directly by callers when needed.
"""

__all__ = ["extract_text_from_mp4"]


def extract_text_from_mp4(*args, **kwargs):
    from tools.video.subtitle_extractor import extract_text_from_mp4 as _impl

    return _impl(*args, **kwargs)
