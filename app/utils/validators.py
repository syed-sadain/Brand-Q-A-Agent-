"""Input validators shared across the ingestion pipeline."""

from __future__ import annotations

from app.core.exceptions import EmptyDocumentError
from app.utils.text_utils import count_words, normalize_whitespace

_MIN_USABLE_WORDS = 20


def normalize_brand(brand: str) -> str:
    """Normalise a brand name to a trimmed, title-cased-agnostic form."""
    return " ".join(brand.split())


def is_usable_text(text: str) -> bool:
    """Return True when the text contains enough real content to be indexed."""
    return count_words(text) >= _MIN_USABLE_WORDS


def ensure_usable_text(text: str, *, source: str) -> str:
    """Normalise ``text`` and raise :class:`EmptyDocumentError` when unusable."""
    normalized = normalize_whitespace(text)
    if not is_usable_text(normalized):
        raise EmptyDocumentError(
            f"The document from '{source}' has too little usable text "
            f"({count_words(normalized)} words); at least {_MIN_USABLE_WORDS} words are required."
        )
    return normalized
