"""Stable document identity.

``doc_id`` is a SHA-256 hash derived deterministically from the tenant and the
content source, so that re-ingesting the same document overwrites rather than
duplicates.
"""

from __future__ import annotations

import hashlib

from app.utils.text_utils import normalize_whitespace


def content_hash(text: str) -> str:
    """Return the SHA-256 hash of the normalised document text."""
    return hashlib.sha256(normalize_whitespace(text).encode("utf-8")).hexdigest()


def compute_doc_id(tenant_id: str, *, url: str | None = None, text_hash: str | None = None) -> str:
    """Compute a stable document id from the tenant and the content source.

    URL documents are identified by their (normalised) URL; raw-text documents
    are identified by the hash of their content. In both cases the tenant is
    part of the identity so identical content in different tenants never
    collides.
    """
    if url is not None:
        identity = f"url::{url.strip().rstrip('/').lower()}"
    elif text_hash is not None:
        identity = f"text::{text_hash}"
    else:  # pragma: no cover - guarded by callers
        raise ValueError("Either 'url' or 'text_hash' must be provided to compute a doc_id.")
    return hashlib.sha256(f"{tenant_id}::{identity}".encode()).hexdigest()
