import httpx
from app.config import settings

_BASE = "https://api.paystack.co"


async def initialize_transaction(
    email: str,
    amount_kobo: int,
    reference: str,
    metadata: dict | None = None,
) -> dict:
    """Initialize a Paystack transaction. Returns the full Paystack response dict."""
    if not settings.paystack_secret_key:
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
        # Dev mode: treat any reference as successful
        return {
            "status": True,
            "data": {"status": "success", "reference": reference, "amount": 0},
        }
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{_BASE}/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {settings.paystack_secret_key}"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
