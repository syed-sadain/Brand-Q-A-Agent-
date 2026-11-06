"""Tests for persistent document-registry writes."""

from __future__ import annotations

import json
import os

from app.repositories.document_repository import DocumentRepository


def test_registry_write_falls_back_when_atomic_replace_is_denied(tmp_path, monkeypatch) -> None:
    path = tmp_path / "document_registry.json"
    repository = DocumentRepository(path)
    repository._cache = {
        "acme": {
            "doc-1": {
                "tenant_id": "acme",
                "doc_id": "doc-1",
                "source": "synthetic://doc-1",
                "brand": "Example",
                "content_hash": "hash-1",
                "chunk_count": 2,
            }
        }
    }

    def deny_replace(_source: str, _destination: str) -> None:
        raise PermissionError("directory replacement is denied")

    monkeypatch.setattr(os, "replace", deny_replace)

    repository._flush_sync()

    assert json.loads(path.read_text(encoding="utf-8")) == repository._cache
