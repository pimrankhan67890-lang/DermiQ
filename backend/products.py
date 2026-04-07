from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
PRODUCTS_CANDIDATES = [ROOT / "products.json", ROOT / "product.json"]


def load_products() -> Dict[str, Any]:
    for p in PRODUCTS_CANDIDATES:
        if p.exists():
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    return payload
            except Exception:
                return {"version": 1, "products": [], "disclaimer": ""}
    return {"version": 1, "products": [], "disclaimer": ""}


def filter_products(payload: Dict[str, Any], condition: str, limit: int = 6) -> List[Dict[str, Any]]:
    items = payload.get("products", [])
    if not isinstance(items, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        conditions = item.get("conditions", [])
        if isinstance(conditions, list) and condition in {str(c) for c in conditions}:
            out.append(item)
    return out[: max(0, int(limit))]


def filter_products_for_labels(payload: Dict[str, Any], labels: List[str], limit: int = 6) -> List[Dict[str, Any]]:
    """
    Returns up to `limit` products that match any of the provided labels (in priority order).
    Duplicates are removed by product id.
    """
    items = payload.get("products", [])
    if not isinstance(items, list):
        return []

    wanted = [str(x).strip() for x in (labels or []) if str(x).strip()]
    if not wanted:
        return []

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for lbl in wanted:
        for item in items:
            if not isinstance(item, dict):
                continue
            pid = str(item.get("id", "")).strip() or str(item.get("name", "")).strip()
            if not pid or pid in seen:
                continue
            conditions = item.get("conditions", [])
            if not isinstance(conditions, list):
                continue
            conds = {str(c).strip() for c in conditions if str(c).strip()}
            if lbl in conds:
                out.append(item)
                seen.add(pid)
                if len(out) >= max(0, int(limit)):
                    return out

    return out


def filter_products_for_top3(payload: Dict[str, Any], top3: List[Dict[str, Any]], limit: int = 6) -> List[Dict[str, Any]]:
    """
    Rank products using top-3 probabilities.

    - Prefer products matching higher-prob labels.
    - Remove duplicates by product id.
    - Return up to `limit` items.
    """
    items = payload.get("products", [])
    if not isinstance(items, list):
        return []

    probs: Dict[str, float] = {}
    for t in top3 or []:
        if not isinstance(t, dict):
            continue
        lbl = str(t.get("label", "")).strip()
        try:
            p = float(t.get("prob", 0.0))
        except Exception:
            p = 0.0
        if lbl:
            probs[lbl] = max(probs.get(lbl, 0.0), p)

    if not probs:
        return []

    scored: List[Tuple[float, str, Dict[str, Any]]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id", "")).strip() or str(item.get("name", "")).strip()
        if not pid:
            continue
        conditions = item.get("conditions", [])
        if not isinstance(conditions, list):
            continue
        conds = {str(c).strip() for c in conditions if str(c).strip()}
        if not conds:
            continue

        # Score: sum of probabilities of matched labels + a small bonus for multiple matches.
        matched = [probs[l] for l in probs.keys() if l in conds]
        if not matched:
            continue
        score = float(sum(matched) + max(0, len(matched) - 1) * 0.05)
        scored.append((score, pid, item))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for _score, pid, item in scored:
        if pid in seen:
            continue
        out.append(item)
        seen.add(pid)
        if len(out) >= max(0, int(limit)):
            break
    return out


def product_buy_links(product: Dict[str, Any]) -> List[Dict[str, str]]:
    links: List[Dict[str, str]] = []
    raw = product.get("buy_links")
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            url = str(item.get("url", "")).strip()
            if name and url:
                links.append({"name": name, "url": url})

    buy_url = str(product.get("buy_url", "")).strip()
    if not links and buy_url:
        links.append({"name": "Buy / View", "url": buy_url})
    return links


def public_product(product: Dict[str, Any]) -> Dict[str, Any]:
    pid = str(product.get("id", "")).strip()
    name = str(product.get("name", "")).strip()
    reason = str(product.get("reason", "")).strip()
    conditions = product.get("conditions", [])
    if not isinstance(conditions, list):
        conditions = []

    # Frontend serves product images from /products/<id>.svg
    image = f"/products/{pid}.svg" if pid else ""

    return {
        "id": pid,
        "name": name,
        "reason": reason,
        "conditions": [str(c) for c in conditions],
        "image": image,
        "buy_links": product_buy_links(product),
    }
