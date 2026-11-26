"""SSRF guard for the places this app requests attacker-influenceable URLs
server-side: AI event drafting from a pasted URL (by moderators, or by agent
connections), the daily scout agent's RSS/listing-page polling, and review
callbacks to agent connections. None should be trusted to only ever point at
the public internet.

Blocks the initial URL and every redirect hop (httpx's automatic redirect
following bypasses a check on the initial URL alone) from resolving to a
private, loopback, link-local, or otherwise non-public address.

Caveat: this validates the hostname's resolved IP at request time, then lets
httpx re-resolve and connect. A DNS server that returns a public IP once and
a private IP moments later (DNS rebinding) can still slip through -- closing
that fully would require connecting directly to the validated IP with SNI/Host
rewriting, which is more machinery than this app's current risk level (an
admin/moderator-gated feature) justifies.
"""
import asyncio
import ipaddress
from urllib.parse import urlparse

import httpx

_MAX_REDIRECTS = 5


class UnsafeURLError(Exception):
    pass


def _is_unsafe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


async def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"Unsupported URL scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise UnsafeURLError("URL has no host")

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(parsed.hostname, None)
    except OSError as e:
        raise UnsafeURLError(f"Could not resolve host {parsed.hostname!r}: {e}")

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if _is_unsafe_ip(ip):
            raise UnsafeURLError(
                f"Refusing to fetch {parsed.hostname!r} -- resolves to a private/internal address"
            )


async def validate_public_url(url: str) -> None:
    """Raise UnsafeURLError unless the URL is http(s) and resolves to a public address."""
    await _validate_url(url)


async def post_json_safely(url: str, body: bytes, *, timeout: float, headers: dict) -> httpx.Response:
    """POST JSON to a URL after checking it resolves to a public address. Redirects are not
    followed (a webhook receiver has no business redirecting a signed POST)."""
    await _validate_url(url)
    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
        return await client.post(url, content=body, headers={**headers, "Content-Type": "application/json"})


async def fetch_safely(url: str, *, timeout: float, user_agent: str) -> httpx.Response:
    """GET a URL, validating it and every redirect hop against private/internal addresses."""
    await _validate_url(url)
    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
        current = url
        for _ in range(_MAX_REDIRECTS + 1):
            resp = await client.get(current, headers={"User-Agent": user_agent})
            if not resp.is_redirect:
                return resp
            location = resp.headers.get("location")
            if not location:
                return resp
            current = str(httpx.URL(current).join(location))
            await _validate_url(current)
        raise UnsafeURLError("Too many redirects")
