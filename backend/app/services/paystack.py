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
    **extra,
) -> dict:
    """Initialize a Paystack transaction. Returns the full Paystack response dict.

    `extra` passes Paystack options straight through, e.g. a split payment to a venue:
    subaccount="ACCT_x", transaction_charge=<Turnup's flat share in kobo>, bearer="subaccount";
    or a subscription: plan="PLN_x"."""
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
                  "metadata": metadata or {}, **{k: v for k, v in extra.items() if v is not None}},
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


# ── Venue marketplace: banks, subaccounts, subscriptions ───────────────────────

async def _get(path: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{_BASE}{path}", params=params,
                             headers={"Authorization": f"Bearer {settings.paystack_secret_key}"},
                             timeout=15)
        r.raise_for_status()
        return r.json()


async def _post(path: str, body: dict, method: str = "POST") -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.request(method, f"{_BASE}{path}", json=body,
                                 headers={"Authorization": f"Bearer {settings.paystack_secret_key}"},
                                 timeout=15)
        r.raise_for_status()
        return r.json()


DEV_BANKS = [
    {"name": "Access Bank", "code": "044"}, {"name": "First Bank of Nigeria", "code": "011"},
    {"name": "Guaranty Trust Bank", "code": "058"}, {"name": "Opay", "code": "999992"},
    {"name": "Kuda Bank", "code": "50211"}, {"name": "Moniepoint MFB", "code": "50515"},
    {"name": "United Bank For Africa", "code": "033"}, {"name": "Zenith Bank", "code": "057"},
]


async def list_banks() -> list[dict]:
    if not settings.paystack_secret_key:
        _require_debug_for_mock("list banks for")
        return DEV_BANKS
    body = await _get("/bank", {"country": "nigeria", "perPage": 200})
    return [{"name": b["name"], "code": b["code"]} for b in body.get("data") or []]


async def resolve_account(account_number: str, bank_code: str) -> str:
    """Returns the account name registered at the bank (Paystack /bank/resolve)."""
    if not settings.paystack_secret_key:
        _require_debug_for_mock("resolve an account for")
        return "DEV ACCOUNT NAME"
    body = await _get("/bank/resolve", {"account_number": account_number, "bank_code": bank_code})
    if not body.get("status"):
        raise RuntimeError(body.get("message") or "Could not resolve that account")
    return body["data"]["account_name"]


async def create_subaccount(business_name: str, bank_code: str, account_number: str,
                            existing_code: str | None = None) -> str:
    """Create (or update) the venue's Paystack subaccount. percentage_charge is 0 because
    Turnup's share is set per payment with transaction_charge."""
    if not settings.paystack_secret_key:
        _require_debug_for_mock("create a subaccount for")
        return existing_code or f"ACCT_dev{account_number[-4:]}"
    payload = {"business_name": business_name[:100], "settlement_bank": bank_code,
               "account_number": account_number, "percentage_charge": 0}
    if existing_code:
        body = await _post(f"/subaccount/{existing_code}", payload, method="PUT")
    else:
        body = await _post("/subaccount", payload)
    if not body.get("status"):
        raise RuntimeError(body.get("message") or "Paystack refused the subaccount")
    return body["data"]["subaccount_code"]


async def create_plan(name: str, amount_kobo: int, interval: str) -> str:
    if not settings.paystack_secret_key:
        _require_debug_for_mock("create a plan for")
        return f"PLN_dev_{interval}_{amount_kobo}"
    body = await _post("/plan", {"name": name, "amount": amount_kobo, "interval": interval})
    return body["data"]["plan_code"]


async def disable_subscription(code: str, email_token: str) -> None:
    if not settings.paystack_secret_key:
        _require_debug_for_mock("cancel a subscription for")
        return
    await _post("/subscription/disable", {"code": code, "token": email_token})
