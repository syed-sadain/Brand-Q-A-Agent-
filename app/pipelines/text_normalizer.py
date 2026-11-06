"""Normalisation of extracted document text."""

from __future__ import annotations

import re

from app.utils.text_utils import normalize_whitespace

_BOILERPLATE_PATTERNS = [
    re.compile(r"(?im)^\s*(cookie|accept all cookies|subscribe to our newsletter).*$"),
    re.compile(r"(?im)^\s*(share this article|advertisement|related articles)[:\s]*$"),
    re.compile(r"(?im)^\s*(sign in|log in|menu|skip to content)\s*$"),
]


def normalize_document_text(text: str) -> str:
    """Normalise whitespace and strip common website boilerplate lines.

    The goal is to reduce noise that would otherwise pollute chunks and hurt
    retrieval quality, without altering the substantive content of the document.
    """
    if not text:
        return ""
    cleaned = text.replace("\u200b", "").replace("\ufeff", "")
    lines = [line for line in cleaned.split("\n") if not _is_boilerplate(line)]
    return normalize_whitespace("\n".join(lines))


def _is_boilerplate(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return any(pattern.match(stripped) for pattern in _BOILERPLATE_PATTERNS)
