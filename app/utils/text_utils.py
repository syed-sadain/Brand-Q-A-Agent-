"""Text normalisation and token estimation helpers."""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # tiktoken ships type information but is an optional dependency.
    from tiktoken import Encoding

_WHITESPACE_RE = re.compile(r"[ \t\u00a0\u2000-\u200a]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WORD_RE = re.compile(r"\w+", re.UNICODE)

_ENCODER: Encoding | None = None
try:  # tiktoken is optional; a heuristic is used when it is unavailable.
    import tiktoken

    _ENCODER = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover - exercised when tiktoken is missing
    _ENCODER = None


def normalize_whitespace(text: str) -> str:
    """Collapse noisy whitespace while preserving paragraph boundaries."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL_RE.sub(" ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def count_tokens(text: str) -> int:
    """Estimate the token count of ``text``.

    Uses ``tiktoken`` when available for accuracy, otherwise falls back to a
    stable approximation (~4 characters per token).
    """
    if not text:
        return 0
    if _ENCODER is not None:
        return len(_ENCODER.encode(text, disallowed_special=()))
    return max(1, (len(text) + 3) // 4)


def count_words(text: str) -> int:
    """Number of word tokens, used to judge whether text is worth indexing."""
    return len(_WORD_RE.findall(text))


def truncate(text: str, max_chars: int) -> str:
    """Truncate ``text`` to ``max_chars`` characters on a word boundary."""
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars]
    last_space = clipped.rfind(" ")
    if last_space > max_chars * 0.6:
        clipped = clipped[:last_space]
    return clipped.rstrip() + "…"
