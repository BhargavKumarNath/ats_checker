"""Stripe Checkout, one-time payment, no accounts (product_requirements.md §3).

Only two calls: create a Checkout Session, verify a webhook. The price lives in Stripe
(`ATSC_STRIPE_PRICE_ID`), never in code, so pricing changes need no deploy.
"""

from __future__ import annotations

from typing import Any

import stripe

from atsc.config import Settings

COMPLETED_EVENT = "checkout.session.completed"


class WebhookError(ValueError):
    pass


def _client(settings: Settings) -> stripe.StripeClient:
    return stripe.StripeClient(settings.stripe_secret_key)


def create_checkout_session(
    settings: Settings, *, job_id: str, success_url: str, cancel_url: str
) -> tuple[str, str]:
    """Return (checkout URL, session id) for one report purchase."""
    session = _client(settings).checkout.sessions.create(
        {
            "mode": "payment",
            "line_items": [{"price": settings.stripe_price_id, "quantity": 1}],
            "client_reference_id": job_id,
            "success_url": success_url,
            "cancel_url": cancel_url,
        }
    )
    if not session.url:
        raise RuntimeError("Stripe returned a session without a URL")
    return session.url, session.id


def verify_webhook(settings: Settings, payload: bytes, sig_header: str) -> Any:
    try:
        return _client(settings).construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except (ValueError, stripe.SignatureVerificationError) as e:
        raise WebhookError(str(e)) from e


def completed_session(event: Any) -> tuple[str, str, str | None] | None:
    """(job id, session id, buyer email) when the event is a completed checkout, else None."""
    if event["type"] != COMPLETED_EVENT:
        return None
    obj = event["data"]["object"]
    job_id = obj.get("client_reference_id")
    if not job_id:
        return None
    details = obj.get("customer_details") or {}
    return str(job_id), str(obj.get("id", "")), details.get("email")
