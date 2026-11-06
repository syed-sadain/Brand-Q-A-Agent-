"""Ingest the sample corpus into the Brand Q&A agent.

Two modes are supported:

``embedded`` (default, offline, no API key required)
    Builds the in-memory vector store and deterministic hashing embeddings
    directly from :class:`app.core.config.Settings`, then runs the real
    :class:`app.services.ingestion_service.IngestionService` against the corpus
    in-process. Nothing leaves the machine.

``--api`` (against a running server)
    Reads the same corpus and ``POST``s it to a running server at
    ``/tenants/{tenant_id}/ingest`` using ``httpx``.

Examples
--------
Offline, in-process (default)::

    .venv\\Scripts\\python.exe scripts\\ingest_sample_data.py --tenant acme

Against a locally running server::

    .venv\\Scripts\\python.exe scripts\\ingest_sample_data.py --tenant acme --api

    .venv\\Scripts\\python.exe scripts\\ingest_sample_data.py --tenant acme \
        --api --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Make ``import app...`` work when run as ``python scripts/ingest_sample_data.py``
# from the project root (or from anywhere else). The project root is the parent
# of this ``scripts/`` directory.
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_CORPUS_PATH = PROJECT_ROOT / "data" / "sample_documents" / "corpus.json"

from app.core.config import Settings  # noqa: E402
from app.core.security import tenant_namespace  # noqa: E402
from app.integrations.embeddings.factory import build_embeddings  # noqa: E402
from app.integrations.vectorstores.factory import build_vector_store  # noqa: E402
from app.repositories.document_repository import DocumentRepository  # noqa: E402
from app.schemas.ingest import IngestDocumentRequest  # noqa: E402
from app.services.ingestion_service import IngestionService  # noqa: E402


def load_corpus(corpus_path: Path) -> list[dict[str, Any]]:
    """Load and lightly validate the sample corpus JSON file.

    Args:
        corpus_path: Path to a JSON array of document objects.

    Returns:
        The parsed list of document dictionaries.

    Raises:
        FileNotFoundError: If the corpus file does not exist.
        ValueError: If the file is not a non-empty JSON array of objects.
    """
    if not corpus_path.exists():
        raise FileNotFoundError(f"Corpus file not found: {corpus_path}")

    with corpus_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, list) or not data:
        raise ValueError(f"Corpus must be a non-empty JSON array: {corpus_path}")
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"Corpus entry #{index} is not a JSON object.")

    return data


def build_ingest_requests(entries: list[dict[str, Any]]) -> list[IngestDocumentRequest]:
    """Convert raw corpus entries into ``IngestDocumentRequest`` objects.

    The contract is ``{"url": null, "text": ..., "source": ..., "brand": ...}``.
    Because ``url`` is ``null``, only ``text``, ``source`` and ``brand`` are
    forwarded to the request model.
    """
    documents: list[IngestDocumentRequest] = []
    for entry in entries:
        documents.append(
            IngestDocumentRequest(
                text=entry["text"],
                source=entry["source"],
                brand=entry["brand"],
            )
        )
    return documents


def build_offline_settings() -> Settings:
    """Build settings for a fully offline run (no API key, no network)."""
    return Settings(
        vector_store_provider="memory",
        embedding_provider="hashing",
        embedding_dimension=256,
    )


async def run_embedded(tenant_id: str, corpus_path: Path) -> int:
    """Ingest the corpus in-process using the in-memory stack.

    Returns a process exit code (``0`` on success).
    """
    settings = build_offline_settings()
    embeddings = build_embeddings(settings)
    vector_store = build_vector_store(settings)
    repository = DocumentRepository(settings.document_registry_path)

    service = IngestionService(
        settings=settings,
        embeddings=embeddings,
        vector_store=vector_store,
        repository=repository,
    )

    entries = load_corpus(corpus_path)
    documents = build_ingest_requests(entries)

    print(f"Corpus:            {corpus_path}")
    print(f"Tenant:            {tenant_id}")
    print(f"Documents loaded:  {len(documents)}")
    print("Mode:              embedded (memory vector store, hashing embeddings)")
    print("-" * 60)

    result = await service.ingest(tenant_id, documents)

    namespace = tenant_namespace(tenant_id)
    vector_count = await vector_store.count(namespace)

    print("Ingestion summary")
    print(f"  documents_stored: {result.documents_stored}")
    print(f"  chunks_stored:    {result.chunks_stored}")
    print(f"  errors:           {len(result.errors)}")
    for error in result.errors:
        print(f"    - {error.get('source')}: {error.get('code')} ({error.get('message')})")
    print(f"  vectors in '{namespace}': {vector_count}")

    return 0


async def run_api(tenant_id: str, corpus_path: Path, base_url: str) -> int:
    """Ingest the corpus by POSTing it to a running server.

    Returns a process exit code (``0`` on success, ``1`` on HTTP failure).
    """
    import httpx  # imported lazily so ``--api`` is the only mode needing it

    entries = load_corpus(corpus_path)
    payload = {
        "documents": [
            {"text": entry["text"], "source": entry["source"], "brand": entry["brand"]}
            for entry in entries
        ]
    }

    endpoint = f"{base_url.rstrip('/')}/tenants/{tenant_id}/ingest"
    print(f"Corpus:      {corpus_path}")
    print(f"Tenant:      {tenant_id}")
    print(f"Documents:   {len(payload['documents'])}")
    print(f"Endpoint:    {endpoint}")
    print("-" * 60)

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(endpoint, json=payload)

    if response.status_code >= 400:
        print(f"Request failed with HTTP {response.status_code}.")
        print(response.text)
        return 1

    try:
        body = response.json()
    except ValueError:
        print("Server returned a non-JSON response:")
        print(response.text)
        return 1

    print("Ingestion response:")
    print(json.dumps(body, indent=2))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Ingest the synthetic sample corpus into the Brand Q&A agent.",
    )
    parser.add_argument(
        "--tenant",
        default="acme",
        help="Tenant id to ingest for (default: acme).",
    )
    parser.add_argument(
        "--api",
        action="store_true",
        help="POST the corpus to a running server instead of ingesting in-process.",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the running server (default: http://localhost:8000).",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS_PATH,
        help=f"Path to corpus.json (default: {DEFAULT_CORPUS_PATH}).",
    )
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    """Entry point. Dispatches to the embedded or API ingestion mode."""
    args = parse_args(argv)
    corpus_path: Path = args.corpus

    if args.api:
        return await run_api(args.tenant, corpus_path, args.base_url)
    return await run_embedded(args.tenant, corpus_path)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
