"""Document loader: fetches and normalises documents into :class:`LoadedDocument`.

URL fetching is asynchronous, size/time bounded and SSRF-safe: every hop in a
redirect chain is re-validated against private/reserved address ranges before it
is followed.
"""

from __future__ import annotations

from urllib.parse import urljoin

import httpx

from app.core.config import Settings
from app.core.exceptions import DocumentFetchError, EmptyDocumentError, UnsafeUrlError
from app.core.logging import get_logger
from app.core.security import validate_url_async
from app.models.document import LoadedDocument
from app.pipelines.document_hasher import compute_doc_id, content_hash
from app.pipelines.text_extractor import extract_readable_text, extract_title
from app.pipelines.text_normalizer import normalize_document_text
from app.utils.validators import ensure_usable_text, normalize_brand

logger = get_logger(__name__)

_TEXT_CONTENT_TYPES = (
    "text/html",
    "text/plain",
    "application/xhtml",
    "application/xml",
    "text/xml",
)


class DocumentLoader:
    """Loads documents from URLs or raw text.

    Reuse a single instance per ingestion batch so HTTP connections are pooled::

        async with DocumentLoader(settings) as loader:
            document = await loader.load(tenant_id, url=..., brand=...)
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> DocumentLoader:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._settings.http_timeout),
            follow_redirects=False,
            headers={"User-Agent": self._settings.http_user_agent},
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------ public
    async def load(
        self,
        tenant_id: str,
        *,
        url: str | None = None,
        text: str | None = None,
        source: str | None = None,
        brand: str | None = None,
    ) -> LoadedDocument:
        """Load a single document from a URL or raw text."""
        brand_name = normalize_brand(brand or "")
        if url is not None:
            html = await self._fetch(url)
            raw_text = extract_readable_text(html)
            title = extract_title(html)
            document_source = source or url
            if title and title.lower() not in raw_text.lower()[:400]:
                raw_text = f"{title}\n\n{raw_text}"
        else:
            if text is None:
                raise EmptyDocumentError("The document has no content.")
            raw_text = text
            document_source = source or "raw-text"

        normalized = normalize_document_text(raw_text)
        normalized = ensure_usable_text(normalized, source=document_source)
        text_digest = content_hash(normalized)
        doc_id = compute_doc_id(
            tenant_id, url=url, text_hash=None if url is not None else text_digest
        )
        return LoadedDocument(
            tenant_id=tenant_id,
            doc_id=doc_id,
            brand=brand_name,
            source=document_source,
            text=normalized,
            content_hash=text_digest,
            is_url_source=url is not None,
        )

    # ------------------------------------------------------------------ internals
    async def _fetch(self, url: str) -> str:
        """Fetch a URL, validating every redirect hop (SSRF protection)."""
        if self._client is None:
            raise DocumentFetchError("The document loader is not initialised.")

        current_url = url
        for _ in range(self._settings.http_max_redirects + 1):
            await validate_url_async(current_url, self._settings)
            try:
                async with self._client.stream("GET", current_url) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise DocumentFetchError(
                                "The server returned a redirect without a location."
                            )
                        current_url = urljoin(current_url, location)
                        continue
                    response.raise_for_status()
                    self._check_content_type(response)
                    return await self._read_bounded(response)
            except UnsafeUrlError:
                raise
            except httpx.TimeoutException as exc:
                raise DocumentFetchError(
                    f"Timed out after {self._settings.http_timeout}s while fetching the document."
                ) from exc
            except httpx.HTTPStatusError as exc:
                raise DocumentFetchError(
                    f"The remote server returned HTTP {exc.response.status_code}."
                ) from exc
            except httpx.HTTPError as exc:
                raise DocumentFetchError("The document could not be retrieved.") from exc
        raise DocumentFetchError("The URL redirected too many times.")

    @staticmethod
    def _check_content_type(response: httpx.Response) -> None:
        content_type = response.headers.get("content-type", "").lower()
        if content_type and not any(token in content_type for token in _TEXT_CONTENT_TYPES):
            raise DocumentFetchError(f"Unsupported content type '{content_type.split(';')[0]}'.")

    async def _read_bounded(self, response: httpx.Response) -> str:
        """Read the body while enforcing the configured maximum size."""
        max_bytes = self._settings.http_max_bytes
        buffer = bytearray()
        async for chunk in response.aiter_bytes():
            buffer.extend(chunk)
            if len(buffer) > max_bytes:
                raise DocumentFetchError(f"The document exceeds the {max_bytes} byte limit.")
        encoding = response.encoding or "utf-8"
        return buffer.decode(encoding, errors="replace")
