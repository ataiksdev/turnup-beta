import logging

import httpx
from app.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://api.paystack.co"


class PaystackConfigError(RuntimeError):
    """Raised when Paystack is unconfigured outside of debug mode -- refuse to auto-succeed
    a real payment rather than silently faking one (see the mock-mode branches below)."""


def _require_debug_for_mock(context: str) -> None:
    if not settings.debug:
        raise PaystackConfigError(
            f"PAYSTACK_SECRET_KEY is not set and debug=False -- refusing to auto-{context} "
            "a real payment. Set the key or enable debug mode for local development."
        )


async def initialize_transaction(
    email: str,
    amount_kobo: int,
    reference: str,
    metadata: dict | None = None,
) -> dict:
    """Initialize a Paystack transaction. Returns the full Paystack response dict."""
    if not settings.paystack_secret_key:
        _require_debug_for_mock("initialize")
        logger.warning(
            "PAYSTACK MOCK MODE (debug=True): faking successful init for %s -- NOT a real payment",
            reference,
        )
        # Dev mode: return a mock response so the flow works without credentials
        return {
            "status": True,
            "data": {
                "reference": reference,
                "authorization_url": f"https://checkout.paystack.com/dev/{reference}",
                "access_code": "dev_access_code",
            },
        }
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{_BASE}/transaction/initialize",
            json={"email": email, "amount": amount_kobo, "reference": reference,
                  "metadata": metadata or {}},
            headers={"Authorization": f"Bearer {settings.paystack_secret_key}"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()


async def verify_transaction(reference: str) -> dict:
    """Verify a Paystack transaction. Returns the full Paystack response dict."""
    if not settings.paystack_secret_key:
        _require_debug_for_mock("verify")
        logger.warning(
            "PAYSTACK MOCK MODE (debug=True): faking successful verify for %s -- NOT a real payment",
            reference,
        )
        # Dev mode: treat any reference as successful
        return {
            "status": True,
            "data": {"status": "success", "reference": reference, "amount": 0, "mock": True},
        }
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{_BASE}/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {settings.paystack_secret_key}"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()


async def refund_transaction(reference: str, amount_kobo: int) -> dict:
    """Refund (part of) a Paystack transaction. `amount_kobo` may be less than the transaction
    total -- one cart checkout is a single transaction covering several orders, so refunding
    one order is a partial refund of that transaction. Paystack processes refunds
    asynchronously; an accepted request comes back with data.status "pending"/"processing"."""
    if not settings.paystack_secret_key:
        _require_debug_for_mock("refund")
        logger.warning(
            "PAYSTACK MOCK MODE (debug=True): faking refund of %s kobo for %s -- NO money moved",
            amount_kobo, reference,
        )
        return {"status": True, "data": {"status": "processed", "mock": True}}
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{_BASE}/refund",
            json={"transaction": reference, "amount": amount_kobo},
            headers={"Authorization": f"Bearer {settings.paystack_secret_key}"},
            timeout=15,
        )
        r.raise_for_status()
        body = r.json()
        if not body.get("status"):
            raise RuntimeError(body.get("message") or "Paystack refused the refund")
        return body
