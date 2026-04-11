from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.affiliate import affiliate_url

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

    label_order = [str(t.get("label", "")).strip() for t in top3 if isinstance(t, dict) and str(t.get("label", "")).strip()]
    primary = label_order[0] if label_order else ""
    tag_bonus_by_label: Dict[str, Dict[str, float]] = {
        "acne": {"salicylic_acid": 0.14, "non_comedogenic": 0.12, "lightweight": 0.08},
        "rosacea": {"mineral": 0.14, "sensitive": 0.12, "fragrance_free": 0.1},
        "eczema": {"ceramides": 0.16, "dryness": 0.12, "sensitive": 0.1},
        "dryness": {"ceramides": 0.14, "dryness": 0.12, "ointment": 0.08},
        "hyperpigmentation": {"tinted": 0.12, "mineral": 0.1, "azelaic_acid": 0.08},
        "psoriasis": {"ointment": 0.14, "dryness": 0.1, "scalp": 0.08},
        "seborrheic_dermatitis": {"scalp": 0.14, "seb_derm": 0.12},
    }
    category_bonus_by_label: Dict[str, Dict[str, float]] = {
        "acne": {"cleanser": 0.08, "treatment": 0.1, "sunscreen": 0.05},
        "rosacea": {"sunscreen": 0.1, "moisturizer": 0.08, "treatment": 0.06},
        "eczema": {"moisturizer": 0.12, "cleanser": 0.06},
        "dryness": {"moisturizer": 0.12, "cleanser": 0.05},
        "hyperpigmentation": {"sunscreen": 0.12, "treatment": 0.08},
        "psoriasis": {"moisturizer": 0.1, "treatment": 0.08},
        "seborrheic_dermatitis": {"treatment": 0.12, "cleanser": 0.05},
    }

    scored: List[Tuple[float, str, str, Dict[str, Any]]] = []
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

        tags = {str(t).strip() for t in item.get("tags", []) if str(t).strip()} if isinstance(item.get("tags"), list) else set()
        category = str(item.get("category", "")).strip().lower()

        # Score: sum of probabilities of matched labels + a small bonus for multiple matches.
        matched = [probs[l] for l in probs.keys() if l in conds]
        if not matched:
            continue
        score = float(sum(matched) + max(0, len(matched) - 1) * 0.05)
        if primary:
            for tag, bonus in tag_bonus_by_label.get(primary, {}).items():
                if tag in tags:
                    score += float(bonus)
            score += float(category_bonus_by_label.get(primary, {}).get(category, 0.0))
            if primary in conds:
                score += 0.08
        try:
            rank = int(item.get("rank", 999) or 999)
        except Exception:
            rank = 999
        score += max(0.0, (1000.0 - float(rank)) / 10000.0)
        scored.append((score, pid, category, item))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    seen_categories: set[str] = set()

    # First pass: diversify categories when possible.
    for _score, pid, category, item in scored:
        if pid in seen:
            continue
        if category and category in seen_categories:
            continue
        out.append(item)
        seen.add(pid)
        if category:
            seen_categories.add(category)
        if len(out) >= max(0, int(limit)):
            return out

    # Second pass: fill remaining slots by score.
    for _score, pid, _category, item in scored:
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
                links.append({"name": name, "url": affiliate_url(name, url)})

    buy_url = str(product.get("buy_url", "")).strip()
    if not links and buy_url:
        links.append({"name": "Buy / View", "url": affiliate_url("buy", buy_url)})
    return links


def public_product(product: Dict[str, Any]) -> Dict[str, Any]:
    pid = str(product.get("id", "")).strip()
    name = str(product.get("name", "")).strip()
    reason = str(product.get("reason", "")).strip()
    conditions = product.get("conditions", [])
    if not isinstance(conditions, list):
        conditions = []

    category = str(product.get("category", "")).strip()
    tags = product.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    pick_badge = str(product.get("pick_badge", "")).strip()
    try:
        rank = int(product.get("rank", 0) or 0)
    except Exception:
        rank = 0

    # Frontend serves product images from /products/<id>.svg
    image = f"/products/{pid}.svg" if pid else ""

    return {
        "id": pid,
        "name": name,
        "reason": reason,
        "category": category,
        "tags": [str(t) for t in tags],
        "pick_badge": pick_badge,
        "rank": rank,
        "conditions": [str(c) for c in conditions],
        "image": image,
        "buy_links": product_buy_links(product),
    }


def list_products(payload: Dict[str, Any], *, category: str = "", limit: int = 100) -> List[Dict[str, Any]]:
    items = payload.get("products", [])
    if not isinstance(items, list):
        return []

    cat = str(category or "").strip().lower()
    out: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if cat:
            c = str(item.get("category", "")).strip().lower()
            if c != cat:
                continue
        out.append(item)

    out.sort(key=lambda p: (int(p.get("rank", 0) or 0), str(p.get("name", "")).lower()))
    lim = max(1, min(int(limit), 300))
    return out[:lim]
