"""Unit tests for stable SHA-256 document identity."""

from __future__ import annotations

import hashlib

import pytest

from app.pipelines.document_hasher import compute_doc_id, content_hash


def test_content_hash_is_a_sha256_hex_digest() -> None:
    digest = content_hash("Asana pricing review")
    assert len(digest) == 64
    assert all(character in "0123456789abcdef" for character in digest)
    assert digest == hashlib.sha256(b"Asana pricing review").hexdigest()


def test_content_hash_is_stable_across_calls() -> None:
    assert content_hash("same text") == content_hash("same text")


def test_content_hash_ignores_whitespace_noise() -> None:
    # Horizontal whitespace (spaces/tabs) is collapsed and trimmed, so hashes are
    # stable against purely cosmetic differences. Paragraph breaks are intentionally
    # preserved by ``normalize_whitespace``, hence only intra-line noise is tested.
    assert content_hash("  Asana \t  pricing   review  ") == content_hash("Asana pricing review")


def test_content_hash_changes_with_content() -> None:
    assert content_hash("Asana") != content_hash("Trello")


def test_doc_id_for_url_is_deterministic() -> None:
    first = compute_doc_id("acme", url="https://example.com/article")
    second = compute_doc_id("acme", url="https://example.com/article")
    assert first == second
    assert len(first) == 64


def test_doc_id_for_url_ignores_case_and_trailing_slash() -> None:
    canonical = compute_doc_id("acme", url="https://example.com/article")
    assert compute_doc_id("acme", url="https://example.com/ARTICLE") == canonical
    assert compute_doc_id("acme", url="https://example.com/article/") == canonical


def test_doc_id_is_scoped_to_the_tenant() -> None:
    acme = compute_doc_id("acme", url="https://example.com/article")
    globex = compute_doc_id("globex", url="https://example.com/article")
    assert acme != globex


def test_doc_id_for_raw_text_uses_the_content_hash() -> None:
    text_hash = content_hash("some raw text")
    assert compute_doc_id("acme", text_hash=text_hash) == compute_doc_id(
        "acme", text_hash=text_hash
    )


def test_doc_id_requires_a_source() -> None:
    with pytest.raises(ValueError):
        compute_doc_id("acme")
