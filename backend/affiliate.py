from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


@dataclass(frozen=True)
class AffiliateConfig:
    amazon_tag: str
    flipkart_affid: str
    pharmeasy_affid: str


def load_affiliate_config() -> AffiliateConfig:
    return AffiliateConfig(
        amazon_tag=str(os.getenv("DERMIQ_AMAZON_TAG", "")).strip(),
        flipkart_affid=str(os.getenv("DERMIQ_FLIPKART_AFFID", "")).strip(),
        pharmeasy_affid=str(os.getenv("DERMIQ_PHARMEASY_AFFID", "")).strip(),
    )


def _set_query_param(url: str, key: str, value: str) -> str:
    """
    Add/replace a single query param.
    """
    p = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k != key]
    q.append((key, value))
    return urlunparse(p._replace(query=urlencode(q, doseq=True)))


def _looks_like_host(host: str, domain: str) -> bool:
    h = str(host or "").lower()
    d = str(domain or "").lower()
    return h == d or h.endswith("." + d)


def affiliate_url(store_name: str, url: str, cfg: Optional[AffiliateConfig] = None) -> str:
    """
    Best-effort affiliate tagging.

    Notes:
    - Only applies tags when the corresponding env vars are set.
    - Does not add extra tracking params to Amazon links to avoid policy issues.
    """
    u = str(url or "").strip()
    if not u:
        return ""

    cfg = cfg or load_affiliate_config()
    store = str(store_name or "").strip().lower()

    try:
        p = urlparse(u)
        host = (p.hostname or "").lower()
    except Exception:
        return u

    # Amazon Associates: append ?tag=YOURTAG-XX
    if (store == "amazon" or _looks_like_host(host, "amazon.com") or _looks_like_host(host, "amazon.in")) and cfg.amazon_tag:
        return _set_query_param(u, "tag", cfg.amazon_tag)

    # Flipkart: append ?affid=YOURID
    if (store == "flipkart" or _looks_like_host(host, "flipkart.com")) and cfg.flipkart_affid:
        return _set_query_param(u, "affid", cfg.flipkart_affid)

    # PharmEasy: no single universal affiliate param. Support optional tag + keep UTMs minimal.
    if (store == "pharmeasy" or _looks_like_host(host, "pharmeasy.in")) and cfg.pharmeasy_affid:
        return _set_query_param(u, "utm_term", cfg.pharmeasy_affid)

    return u

