"""Readable-text extraction from HTML."""

from __future__ import annotations

from bs4 import BeautifulSoup

from app.utils.text_utils import normalize_whitespace

_NOISE_TAGS = ("script", "style", "noscript", "template", "svg", "iframe", "form", "nav", "footer")


def extract_readable_text(html: str) -> str:
    """Extract the main readable text from an HTML document.

    Uses BeautifulSoup with the fast ``lxml`` parser. Boilerplate containers
    (scripts, styles, navigation, footers, forms) are removed before extracting
    text so that chunks contain article content rather than chrome.
    """
    if not html or not html.strip():
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(_NOISE_TAGS):
        tag.decompose()
    for selector in ("header", "aside"):
        for element in soup.find_all(selector):
            element.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text(separator="\n")
    return normalize_whitespace(text)


def extract_title(html: str) -> str:
    """Return the document ``<title>`` if present, otherwise an empty string."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return normalize_whitespace(soup.title.get_text()) if soup.title else ""
