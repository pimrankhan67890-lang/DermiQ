from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse


@dataclass(frozen=True)
class OutgoingUrlCheck:
    ok: bool
    reason: str
    host: str


_ALLOWED_HOSTS = {
    # Amazon India
    "amazon.in",
    "www.amazon.in",
    "m.amazon.in",
    # Flipkart
    "flipkart.com",
    "www.flipkart.com",
    # PharmEasy
    "pharmeasy.in",
    "www.pharmeasy.in",
}


def validate_outgoing_url(url: str) -> OutgoingUrlCheck:
    u = str(url or "").strip()
    if not u:
        return OutgoingUrlCheck(False, "missing_url", "")
    try:
        p = urlparse(u)
    except Exception:
        return OutgoingUrlCheck(False, "invalid_url", "")

    if p.scheme not in {"http", "https"}:
        return OutgoingUrlCheck(False, "invalid_scheme", p.hostname or "")

    host = (p.hostname or "").lower()
    if not host:
        return OutgoingUrlCheck(False, "missing_host", "")

    if host not in _ALLOWED_HOSTS:
        return OutgoingUrlCheck(False, "host_not_allowed", host)

    return OutgoingUrlCheck(True, "", host)


def normalize_store(store: str, host: str) -> str:
    s = str(store or "").strip().lower()
    if s in {"amazon", "amazon.in"}:
        return "Amazon"
    if s in {"flipkart"}:
        return "Flipkart"
    if s in {"pharmeasy", "pharm easy"}:
        return "PharmEasy"

    h = str(host or "").lower()
    if "amazon." in h:
        return "Amazon"
    if "flipkart." in h:
        return "Flipkart"
    if "pharmeasy." in h:
        return "PharmEasy"
    return "Store"

