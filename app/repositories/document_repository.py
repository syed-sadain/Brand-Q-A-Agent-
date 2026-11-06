"""Document registry.

Tracks, per tenant, which documents have been ingested and how many chunks each
one produced. This is what makes re-ingestion idempotent and lets the ingestion
service delete *obsolete* vectors when a document's chunk count shrinks.

The default implementation persists to a JSON file so the registry survives
restarts. Writes use atomic replacement when the filesystem permits it. Some
Windows/OneDrive folders deny replacement while allowing writes to the existing
file; those locations use a locked in-place fallback. Pass ``path=None`` for an
ephemeral, process-local registry (used by tests).
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from app.core.exceptions import VectorStoreError
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class DocumentRecord:
    """Registry entry for a single ingested document."""

    tenant_id: str
    doc_id: str
    source: str
    brand: str
    content_hash: str
    chunk_count: int


class DocumentRepository:
    """Thread/async-safe registry of ingested documents."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else None
        self._lock = asyncio.Lock()
        self._cache: dict[str, dict[str, dict]] = {}
        self._loaded = False

    # ------------------------------------------------------------------ storage
    def _load_sync(self) -> dict[str, dict[str, dict]]:
        if self._path is None or not self._path.exists():
            return {}
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "document registry unreadable, starting empty", extra={"error": str(exc)}
            )
            return {}

    def _flush_sync(self) -> None:
        if self._path is None:
            return
        temp_name: str | None = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temp_dir = Path(tempfile.gettempdir())
            try:
                same_filesystem = os.stat(temp_dir).st_dev == os.stat(self._path.parent).st_dev
            except OSError:
                same_filesystem = False
            if not same_filesystem:
                temp_dir = self._path.parent
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=temp_dir, delete=False, suffix=".tmp"
            ) as handle:
                json.dump(self._cache, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
                temp_name = handle.name
            try:
                os.replace(temp_name, self._path)
                temp_name = None
            except PermissionError:
                # OneDrive and some managed Windows folders deny delete-child
                # permission on the directory, which makes os.replace fail even
                # when the existing registry file itself is writable. Keep the
                # in-process lock and update that file directly as a fallback.
                with self._path.open("w", encoding="utf-8") as handle:
                    json.dump(self._cache, handle, ensure_ascii=False)
                    handle.flush()
                    os.fsync(handle.fileno())
        except OSError as exc:
            raise VectorStoreError("Failed to persist the document registry.") from exc
        finally:
            if temp_name is not None:
                try:
                    os.unlink(temp_name)
                except OSError as exc:
                    logger.warning(
                        "unable to clean temporary registry file", extra={"error": str(exc)}
                    )

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        async with self._lock:
            if not self._loaded:
                self._cache = await asyncio.to_thread(self._load_sync)
                self._loaded = True

    # ------------------------------------------------------------------ api
    async def upsert(self, record: DocumentRecord) -> None:
        await self._ensure_loaded()
        async with self._lock:
            tenant_docs = self._cache.setdefault(record.tenant_id, {})
            tenant_docs[record.doc_id] = asdict(record)
            await asyncio.to_thread(self._flush_sync)

    async def get(self, tenant_id: str, doc_id: str) -> DocumentRecord | None:
        await self._ensure_loaded()
        raw = self._cache.get(tenant_id, {}).get(doc_id)
        return DocumentRecord(**raw) if raw else None

    async def list_documents(self, tenant_id: str) -> list[DocumentRecord]:
        await self._ensure_loaded()
        return [DocumentRecord(**raw) for raw in self._cache.get(tenant_id, {}).values()]

    async def count_documents(self, tenant_id: str) -> int:
        await self._ensure_loaded()
        return len(self._cache.get(tenant_id, {}))
