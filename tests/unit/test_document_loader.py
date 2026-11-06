"""Unit tests for the async, SSRF-guarded document loader."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.core.config import Settings
from app.core.exceptions import DocumentFetchError
from app.pipelines.document_loader import DocumentLoader

_ARTICLE = (
    "<html><head><title>Project management tools compared</title></head><body><main>"
    "<p>Asana and Trello are compared across pricing, features and reviewer opinions for "
    "small teams in this detailed project management software article.</p>"
    "</main></body></html>"
)


@respx.mock
async def test_fetch_extracts_readable_text(settings: Settings, allow_all_urls) -> None:
    respx.get("https://example.com/article").mock(
        return_value=httpx.Response(200, html=_ARTICLE, headers={"content-type": "text/html"})
    )
    async with DocumentLoader(settings) as loader:
        document = await loader.load("acme", url="https://example.com/article", brand="Asana")

    assert document.is_url_source
    assert "Asana and Trello" in document.text
    assert document.source == "https://example.com/article"


@respx.mock
async def test_title_is_prepended_when_absent_from_body(settings: Settings, allow_all_urls) -> None:
    respx.get("https://example.com/titled").mock(
        return_value=httpx.Response(200, html=_ARTICLE, headers={"content-type": "text/html"})
    )
    async with DocumentLoader(settings) as loader:
        document = await loader.load("acme", url="https://example.com/titled", brand="Asana")
    assert document.text.startswith("Project management tools compared")


@respx.mock
async def test_redirects_are_followed_and_revalidated(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    validated: list[str] = []

    async def _record(url: str, _settings: Settings) -> str:
        validated.append(url)
        return url

    monkeypatch.setattr("app.pipelines.document_loader.validate_url_async", _record)

    respx.get("https://example.com/start").mock(
        return_value=httpx.Response(302, headers={"location": "https://example.com/final"})
    )
    respx.get("https://example.com/final").mock(
        return_value=httpx.Response(200, html=_ARTICLE, headers={"content-type": "text/html"})
    )

    async with DocumentLoader(settings) as loader:
        document = await loader.load("acme", url="https://example.com/start", brand="Asana")

    assert "Asana and Trello" in document.text
    assert validated == ["https://example.com/start", "https://example.com/final"]


@respx.mock
async def test_non_text_content_type_is_rejected(settings: Settings, allow_all_urls) -> None:
    respx.get("https://example.com/file.pdf").mock(
        return_value=httpx.Response(
            200, content=b"%PDF-1.7 binary", headers={"content-type": "application/pdf"}
        )
    )
    async with DocumentLoader(settings) as loader:
        with pytest.raises(DocumentFetchError):
            await loader.load("acme", url="https://example.com/file.pdf", brand="Asana")


@respx.mock
async def test_oversized_document_is_rejected(settings: Settings, allow_all_urls) -> None:
    small_settings = settings.model_copy(update={"http_max_bytes": 200})
    respx.get("https://example.com/huge").mock(
        return_value=httpx.Response(
            200,
            html="<html><body>" + ("x" * 5000) + "</body></html>",
            headers={"content-type": "text/html"},
        )
    )
    async with DocumentLoader(small_settings) as loader:
        with pytest.raises(DocumentFetchError):
            await loader.load("acme", url="https://example.com/huge", brand="Asana")


@respx.mock
async def test_http_error_status_is_reported(settings: Settings, allow_all_urls) -> None:
    respx.get("https://example.com/missing").mock(return_value=httpx.Response(404))
    async with DocumentLoader(settings) as loader:
        with pytest.raises(DocumentFetchError):
            await loader.load("acme", url="https://example.com/missing", brand="Asana")


@respx.mock
async def test_too_many_redirects_is_reported(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _allow(url: str, _settings: Settings) -> str:
        return url

    monkeypatch.setattr("app.pipelines.document_loader.validate_url_async", _allow)
    respx.get(url__regex=r"https://example\.com/loop.*").mock(
        return_value=httpx.Response(302, headers={"location": "https://example.com/loop"})
    )
    async with DocumentLoader(settings) as loader:
        with pytest.raises(DocumentFetchError):
            await loader.load("acme", url="https://example.com/loop", brand="Asana")


async def test_raw_text_document_is_loaded_without_network(settings: Settings) -> None:
    text = (
        "Asana is described by reviewers as powerful for complex workflows while Trello is "
        "described as simpler and cheaper for small teams."
    )
    async with DocumentLoader(settings) as loader:
        document = await loader.load(
            "acme", text=text, source="synthetic://manual-1", brand="Asana"
        )
    assert not document.is_url_source
    assert document.source == "synthetic://manual-1"
    assert "powerful for complex workflows" in document.text
