from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional, Tuple

from backend.tracker import DB_PATH, init_db, touch_session


@dataclass(frozen=True)
class BillingStatus:
    plan: str  # "free" | "pro"
    pro_token: str


def _now() -> int:
    return int(time.time())


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH.as_posix(), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def get_billing_status(session_id: str) -> BillingStatus:
    sid = str(session_id or "").strip()
    if not sid:
        return BillingStatus("free", "")
    init_db()
    touch_session(sid)
    c = _conn()
    try:
        cur = c.execute(
            "SELECT p.pro_token AS token, a.active AS active "
            "FROM pro_links p JOIN pro_accounts a ON a.pro_token=p.pro_token "
            "WHERE p.session_id=? LIMIT 1",
            (sid,),
        )
        row = cur.fetchone()
        if row is None:
            return BillingStatus("free", "")
        token = str(row["token"] or "")
        active = int(row["active"] or 0)
        if token and active == 1:
            return BillingStatus("pro", token)
        return BillingStatus("free", "")
    finally:
        c.close()


def link_session_to_pro_token(session_id: str, pro_token: str) -> bool:
    sid = str(session_id or "").strip()
    tok = str(pro_token or "").strip()
    if not sid or not tok:
        return False
    init_db()
    touch_session(sid)
    now = _now()
    c = _conn()
    try:
        cur = c.execute("SELECT pro_token, active FROM pro_accounts WHERE pro_token=? LIMIT 1", (tok,))
        row = cur.fetchone()
        if row is None or int(row["active"] or 0) != 1:
            return False
        c.execute(
            "INSERT INTO pro_links(session_id, pro_token, linked_at) VALUES(?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET pro_token=excluded.pro_token, linked_at=excluded.linked_at",
            (sid, tok, now),
        )
        c.commit()
        return True
    finally:
        c.close()


def create_manual_pro_for_session(session_id: str) -> str:
    """
    Create a Pro token and link it to the given session.
    """
    sid = str(session_id or "").strip()
    if not sid:
        return ""
    init_db()
    touch_session(sid)
    tok = "pro_" + secrets.token_urlsafe(24)
    now = _now()
    c = _conn()
    try:
        c.execute(
            "INSERT OR REPLACE INTO pro_accounts(pro_token, created_at, source, active) VALUES(?,?,?,1)",
            (tok, now, "manual"),
        )
        c.execute(
            "INSERT INTO pro_links(session_id, pro_token, linked_at) VALUES(?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET pro_token=excluded.pro_token, linked_at=excluded.linked_at",
            (sid, tok, now),
        )
        c.commit()
        return tok
    finally:
        c.close()


def _stripe_enabled() -> bool:
    return bool(str(os.getenv("STRIPE_SECRET_KEY", "")).strip() and str(os.getenv("STRIPE_PRICE_ID", "")).strip())


def stripe_create_checkout_url(session_id: str) -> Tuple[Optional[str], str]:
    """
    Create a Stripe Checkout Session (subscription) without using the stripe SDK.
    Returns (url, error_message).
    """
    if not _stripe_enabled():
        return None, "Stripe billing is not configured."

    sid = str(session_id or "").strip()
    if not sid:
        return None, "Missing session."

    secret_key = str(os.getenv("STRIPE_SECRET_KEY", "")).strip()
    price_id = str(os.getenv("STRIPE_PRICE_ID", "")).strip()
    success_url = str(os.getenv("STRIPE_SUCCESS_URL", "")).strip()
    cancel_url = str(os.getenv("STRIPE_CANCEL_URL", "")).strip()
    if not success_url or not cancel_url:
        return None, "Missing STRIPE_SUCCESS_URL / STRIPE_CANCEL_URL."

    form = {
        "mode": "subscription",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": sid,
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "allow_promotion_codes": "true",
    }

    data = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        method="POST",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {secret_key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # nosec - URL is fixed to Stripe
            payload = json.loads(resp.read().decode("utf-8"))
            url = str(payload.get("url", "")).strip()
            if not url:
                return None, "Stripe did not return a checkout URL."
            return url, ""
    except Exception as e:
        return None, f"Stripe error: {e}"


def _verify_stripe_signature(payload: bytes, sig_header: str, secret: str, tolerance_seconds: int = 300) -> bool:
    """
    Verify Stripe webhook signature.
    """
    secret = str(secret or "").strip()
    sig_header = str(sig_header or "").strip()
    if not secret or not sig_header:
        return False

    parts = {}
    for item in sig_header.split(","):
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        parts.setdefault(k.strip(), []).append(v.strip())

    try:
        ts = int(parts.get("t", ["0"])[0])
    except Exception:
        return False

    # Replay protection
    now = _now()
    if abs(now - ts) > int(tolerance_seconds):
        return False

    signed_payload = f"{ts}.".encode("utf-8") + payload
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    sigs = parts.get("v1", [])
    return any(hmac.compare_digest(expected, s) for s in sigs)


def stripe_handle_webhook(raw_body: bytes, sig_header: str) -> Tuple[bool, str]:
    secret = str(os.getenv("STRIPE_WEBHOOK_SECRET", "")).strip()
    if not secret:
        return False, "Missing STRIPE_WEBHOOK_SECRET."
    if not _verify_stripe_signature(raw_body, sig_header, secret):
        return False, "Invalid signature."

    try:
        event = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return False, "Invalid JSON."

    etype = str(event.get("type", "")).strip()
    obj = (((event.get("data") or {}).get("object")) if isinstance(event.get("data"), dict) else None) or {}
    if not isinstance(obj, dict):
        obj = {}

    if etype != "checkout.session.completed":
        return True, "ignored"

    sid = str(obj.get("client_reference_id", "")).strip()
    if not sid:
        return False, "Missing client_reference_id."

    subscription_id = str(obj.get("subscription", "")).strip()
    customer_id = str(obj.get("customer", "")).strip()
    email = str(obj.get("customer_details", {}).get("email", "") if isinstance(obj.get("customer_details"), dict) else "").strip()

    # Create a Pro token and link it to this session.
    init_db()
    touch_session(sid)
    tok = "pro_" + secrets.token_urlsafe(24)
    now = _now()
    c = _conn()
    try:
        c.execute(
            "INSERT OR REPLACE INTO pro_accounts("
            "pro_token, created_at, source, stripe_customer_id, stripe_subscription_id, stripe_email, active"
            ") VALUES(?,?,?,?,?,?,1)",
            (tok, now, "stripe", customer_id or None, subscription_id or None, email or None),
        )
        c.execute(
            "INSERT INTO pro_links(session_id, pro_token, linked_at) VALUES(?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET pro_token=excluded.pro_token, linked_at=excluded.linked_at",
            (sid, tok, now),
        )
        c.commit()
    finally:
        c.close()

    return True, "ok"
