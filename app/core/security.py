"""Security helpers: tenant validation, SSRF-safe URL checks and namespacing.

These helpers are used by both the API layer and the ingestion pipeline so that
security is enforced close to the data layer, not only at the route handler.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from ipaddress import IPv4Address, IPv6Address
from urllib.parse import urlsplit

from app.core.config import Settings
from app.core.exceptions import InvalidTenantError, UnsafeUrlError

_TENANT_RE = re.compile(r"^[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?$")

_BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata.goog",
}


def validate_tenant_id(tenant_id: str) -> str:
    """Validate and normalise a tenant identifier.

    Tenant ids are used to derive vector store namespaces, so they are restricted
    to a conservative character set to prevent namespace injection.
    """
    candidate = (tenant_id or "").strip().lower()
    if not _TENANT_RE.match(candidate):
        raise InvalidTenantError(
            "tenant_id must be 1-64 characters, start and end with a letter or "
            "digit, and contain only lowercase letters, digits, '-' or '_'."
        )
    return candidate


def tenant_namespace(tenant_id: str) -> str:
    """Derive a deterministic vector-store namespace from a validated tenant id."""
    return f"tenant-{validate_tenant_id(tenant_id)}"


def _is_blocked_ip(ip: IPv4Address | IPv6Address) -> bool:
    """Return True for IPs that must never be fetched (SSRF protection)."""
    if isinstance(ip, IPv6Address) and ip.ipv4_mapped is not None:
        return _is_blocked_ip(ip.ipv4_mapped)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _validate_scheme_and_host(url: str, settings: Settings) -> tuple[str, str]:
    parts = urlsplit(url.strip())
    if parts.scheme not in settings.allowed_url_schemes:
        raise UnsafeUrlError(f"Only {', '.join(settings.allowed_url_schemes)} URLs are supported.")
    if not parts.hostname:
        raise UnsafeUrlError("The URL must include a hostname.")
    host = parts.hostname.lower()
    if host in _BLOCKED_HOSTNAMES or host.endswith(".localhost") or host.endswith(".local"):
        raise UnsafeUrlError("Fetching local or internal hostnames is not allowed.")
    return parts.geturl(), host


def _check_literal_ip(host: str, settings: Settings) -> None:
    """Reject direct IP literals that point at non-public ranges."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if _is_blocked_ip(ip) and not settings.allow_private_networks:
        raise UnsafeUrlError("Fetching private or reserved IP addresses is not allowed.")


async def _resolve_host(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None)
    except socket.gaierror as exc:  # pragma: no cover - depends on DNS
        raise UnsafeUrlError(f"Could not resolve host '{host}'.") from exc
    return list({str(info[4][0]) for info in infos})


async def validate_url_async(url: str, settings: Settings) -> str:
    """Fully validate a URL, including DNS resolution against private ranges.

    Redirect destinations must be re-validated with this same function, which is
    why the check lives here rather than inside a single HTTP client call.
    """
    normalised, host = _validate_scheme_and_host(url, settings)
    _check_literal_ip(host, settings)
    addresses = await _resolve_host(host)
    if not addresses:
        raise UnsafeUrlError("The URL hostname did not resolve to any address.")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if _is_blocked_ip(ip) and not settings.allow_private_networks:
            raise UnsafeUrlError("The URL resolves to a private or reserved address.")
    return normalised


def validate_url_sync(url: str, settings: Settings) -> str:
    """Structural URL validation without DNS resolution.

    Used for fast fail responses; :func:`validate_url_async` remains the
    authoritative check performed immediately before fetching.
    """
    normalised, host = _validate_scheme_and_host(url, settings)
    _check_literal_ip(host, settings)
    return normalised
