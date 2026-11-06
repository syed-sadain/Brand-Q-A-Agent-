"""Unit tests for tenant validation, namespacing and SSRF protection."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.exceptions import InvalidTenantError, UnsafeUrlError
from app.core.security import (
    tenant_namespace,
    validate_tenant_id,
    validate_url_async,
    validate_url_sync,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(embedding_provider="hashing", embedding_dimension=32)


# ---------------------------------------------------------------- tenant ids
@pytest.mark.parametrize("tenant", ["acme", "a", "tenant-1", "tenant_1", "acme2026", "x" * 64])
def test_valid_tenant_ids_are_accepted(tenant: str, settings: Settings) -> None:
    assert validate_tenant_id(tenant) == tenant


def test_tenant_id_is_lowercased_and_trimmed() -> None:
    assert validate_tenant_id("  ACME  ") == "acme"


@pytest.mark.parametrize(
    "tenant",
    ["", "-acme", "acme-", "ac me", "ac.me", "acme/../globex", "acme$", "x" * 65, "café"],
)
def test_invalid_tenant_ids_are_rejected(tenant: str) -> None:
    with pytest.raises(InvalidTenantError):
        validate_tenant_id(tenant)


def test_namespace_is_derived_from_the_validated_tenant() -> None:
    assert tenant_namespace("acme") == "tenant-acme"
    assert tenant_namespace("Acme") == "tenant-acme"


def test_namespace_rejects_invalid_tenants() -> None:
    with pytest.raises(InvalidTenantError):
        tenant_namespace("bad tenant")


# ---------------------------------------------------------------- URL safety
def test_public_https_url_is_allowed(settings: Settings) -> None:
    assert (
        validate_url_sync("https://example.com/article", settings) == "https://example.com/article"
    )


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "gopher://example.com",
    ],
)
def test_unsupported_schemes_are_rejected(url: str, settings: Settings) -> None:
    with pytest.raises(UnsafeUrlError):
        validate_url_sync(url, settings)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://localhost.localdomain/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://something.local/",
        "http://api.localhost/",
    ],
)
def test_internal_hostnames_are_rejected(url: str, settings: Settings) -> None:
    with pytest.raises(UnsafeUrlError):
        validate_url_sync(url, settings)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
    ],
)
def test_private_and_link_local_ip_literals_are_rejected(url: str, settings: Settings) -> None:
    with pytest.raises(UnsafeUrlError):
        validate_url_sync(url, settings)


def test_missing_hostname_is_rejected(settings: Settings) -> None:
    with pytest.raises(UnsafeUrlError):
        validate_url_sync("http:///path", settings)


def test_private_networks_can_be_opted_in_for_local_testing() -> None:
    settings = Settings(
        embedding_provider="hashing",
        embedding_dimension=32,
        allow_private_networks=True,
    )
    # The literal-IP guard is skipped when private networks are explicitly allowed.
    assert validate_url_sync("http://127.0.0.1:9000/", settings)


async def test_async_validation_rejects_private_ip_without_dns(settings: Settings) -> None:
    with pytest.raises(UnsafeUrlError):
        await validate_url_async("http://192.168.0.10/", settings)


async def test_async_validation_rejects_bad_scheme(settings: Settings) -> None:
    with pytest.raises(UnsafeUrlError):
        await validate_url_async("file:///etc/hosts", settings)
