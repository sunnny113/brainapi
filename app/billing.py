import hashlib
import hmac
from decimal import Decimal, ROUND_HALF_UP

import httpx

from .auth import get_db_api_key, set_db_api_key_paid
from .config import settings


class BillingError(Exception):
    pass


def _ensure_razorpay_keys() -> None:
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise BillingError("Razorpay is not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET")


def amount_inr_to_paise(amount_inr: float) -> int:
    value = (Decimal(str(amount_inr)) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    paise = int(value)
    if paise <= 0:
        raise BillingError("Amount must be greater than zero")
    return paise


def create_razorpay_order(
    *,
    api_key_id: str,
    amount_inr: float,
    plan_name: str,
    customer_name: str | None,
    customer_email: str | None,
    customer_phone: str | None,
) -> dict:
    _ensure_razorpay_keys()

    key_info = get_db_api_key(api_key_id)
    if key_info is None:
        raise BillingError("API key not found")
    if not key_info["is_active"]:
        raise BillingError("API key is inactive")

    amount_paise = amount_inr_to_paise(amount_inr)

    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "receipt": f"brainapi_{api_key_id[:8]}",
        "notes": {
            "api_key_id": api_key_id,
            "plan_name": plan_name,
            "customer_name": customer_name or "",
            "customer_email": customer_email or "",
            "customer_phone": customer_phone or "",
        },
    }

    with httpx.Client(timeout=20.0) as client:
        response = client.post(
            "https://api.razorpay.com/v1/orders",
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
            json=payload,
        )

    if response.status_code >= 400:
        raise BillingError(f"Razorpay order create failed: HTTP {response.status_code}")

    body = response.json()
    return {
        "order_id": body.get("id", ""),
        "amount_inr": amount_inr,
        "amount_paise": amount_paise,
        "currency": "INR",
        "key_id": settings.razorpay_key_id,
        "api_key_id": api_key_id,
        "plan_name": plan_name,
    }


def verify_razorpay_signature(order_id: str, payment_id: str, signature: str) -> bool:
    if not settings.razorpay_key_secret:
        raise BillingError("Razorpay secret is not configured")
    body = f"{order_id}|{payment_id}".encode("utf-8")
    digest = hmac.new(settings.razorpay_key_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def verify_and_mark_paid(api_key_id: str, order_id: str, payment_id: str, signature: str) -> bool:
    if not verify_razorpay_signature(order_id, payment_id, signature):
        return False

    updated = set_db_api_key_paid(api_key_id, is_paid=True)
    return updated is not None


def verify_razorpay_webhook_signature(raw_body: bytes, signature: str) -> bool:
    if not settings.razorpay_webhook_secret:
        raise BillingError("Razorpay webhook secret is not configured")
    digest = hmac.new(settings.razorpay_webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def handle_razorpay_webhook(payload: dict, signature: str, raw_body: bytes) -> dict:
    if not verify_razorpay_webhook_signature(raw_body=raw_body, signature=signature):
        raise BillingError("Invalid Razorpay webhook signature")

    event = payload.get("event", "")
    payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    notes = payment_entity.get("notes", {}) if isinstance(payment_entity, dict) else {}
    api_key_id = notes.get("api_key_id")

    marked_paid = False
    if event == "payment.captured" and api_key_id:
        marked_paid = set_db_api_key_paid(api_key_id, is_paid=True) is not None

    return {
        "received": True,
        "event": event,
        "api_key_id": api_key_id,
        "marked_paid": marked_paid,
    }
