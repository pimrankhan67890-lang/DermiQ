from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RoutinePlan:
    headline: str
    today_focus: str
    am: List[str]
    pm: List[str]
    weekly: List[str]
    avoid: List[str]
    timeline: str
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _uniq(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        s = str(x or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def build_routine_plan(
    *,
    top_label: str,
    selected_products: List[Dict[str, Any]],
    prefs: Optional[Dict[str, Any]] = None,
) -> RoutinePlan:
    """
    Safety-first routine generator. Educational only.
    """
    label = str(top_label or "").strip().lower()
    prefs = prefs or {}
    sensitive = bool(prefs.get("sensitive_skin", False))
    fragrance_free = bool(prefs.get("fragrance_free", True))
    pregnancy_safe = bool(prefs.get("pregnancy_safe", False))
    note = str(prefs.get("note", "")).strip()
    preferred_store = str(prefs.get("preferred_store", "")).strip()

    cats = {str(p.get("category", "")).strip().lower() for p in (selected_products or []) if isinstance(p, dict)}
    has_cleanser = "cleanser" in cats
    has_moist = "moisturizer" in cats
    has_spf = "sunscreen" in cats
    has_treat = "treatment" in cats
    product_count = len([p for p in (selected_products or []) if isinstance(p, dict)])

    am: List[str] = []
    pm: List[str] = []
    weekly: List[str] = []
    avoid: List[str] = []
    notes: List[str] = []

    # Universal basics
    am.append("Cleanse gently (lukewarm water).") if has_cleanser else am.append("Rinse + cleanse gently if needed.")
    if has_moist:
        am.append("Moisturize (thin layer).")
    else:
        am.append("Moisturize if skin feels tight or dry.")
    if has_spf:
        am.append("Apply sunscreen (SPF 30+) and reapply if outdoors.")
    else:
        am.append("If outdoors: use sunscreen (SPF 30+).")

    pm.append("Cleanse gently (remove sunscreen/makeup).") if has_cleanser else pm.append("Cleanse gently in the evening.")
    if has_treat:
        pm.append("Apply your treatment as directed (start 2–3 nights/week, then increase slowly).")
    pm.append("Moisturize to support skin barrier.") if has_moist else pm.append("Moisturize if needed.")

    weekly.append("Patch-test new products (small area) before full use.")
    weekly.append("Take 1 progress photo weekly in the same lighting.")

    if fragrance_free:
        avoid.append("Avoid strongly fragranced products if you notice irritation.")
    if sensitive:
        avoid.append("Avoid introducing multiple new products at once.")
        notes.append("Sensitive skin tip: introduce one product at a time for 5–7 days.")

    # Condition-specific adjustments (educational)
    if label == "acne":
        notes.append("Acne often improves slowly—give changes 6–8 weeks.")
        avoid.append("Avoid heavy occlusive products if they clog pores for you.")
        avoid.append("Don’t pick or scrub—this can worsen inflammation and marks.")
    elif label == "rosacea":
        notes.append("Rosacea often flares with triggers—track heat, sun, alcohol, spicy foods, and stress.")
        avoid.append("Avoid harsh exfoliants if they sting or worsen redness.")
        if has_spf:
            notes.append("Prefer mineral sunscreen if chemical sunscreens sting.")
    elif label == "eczema" or label == "dryness":
        notes.append("Barrier repair matters most—moisturize consistently for 2–4 weeks.")
        avoid.append("Avoid long hot showers; keep showers short and lukewarm.")
        avoid.append("Stop any product that burns, itches more, or worsens rash.")
    elif label == "hyperpigmentation":
        notes.append("Sun protection is the #1 step for hyperpigmentation—results take 8–12 weeks.")
        avoid.append("Avoid aggressive scrubs; they can worsen pigmentation in some skin types.")
    elif label == "psoriasis":
        notes.append("Psoriasis can mimic other rashes—consider clinician confirmation, especially if widespread.")
    elif label == "seborrheic_dermatitis":
        notes.append("Seb derm often needs consistent gentle care; if scalp/face is involved, consider clinician advice.")

    if pregnancy_safe:
        notes.append("Pregnancy-safe preference enabled: avoid starting strong actives unless cleared by a clinician.")
        avoid.append("Avoid retinoids unless a clinician specifically approves.")

    if preferred_store:
        notes.append(f"Preferred store selected: {preferred_store}. Compare formula details before buying.")
    if note:
        notes.append(f"User note: {note}")

    headline_map = {
        "acne": "Calm breakouts without over-drying your skin.",
        "rosacea": "Protect the barrier and reduce flare triggers.",
        "eczema": "Repair the barrier first and keep the routine gentle.",
        "dryness": "Restore moisture consistently and reduce irritation.",
        "hyperpigmentation": "Protect from UV and stay steady for more even tone.",
        "psoriasis": "Support scaling-prone skin and watch for warning signs.",
        "seborrheic_dermatitis": "Keep care gentle and consistent around flakes and oil-prone areas.",
    }
    focus_map = {
        "acne": "Start treatment nights slowly, keep sunscreen daily, and avoid picking.",
        "rosacea": "Prioritize gentle cleansing, mineral SPF, and trigger tracking.",
        "eczema": "Moisturize soon after washing and stop anything that stings.",
        "dryness": "Use fewer products, more moisture, and avoid over-cleansing.",
        "hyperpigmentation": "Daily sunscreen matters more than adding too many actives at once.",
        "psoriasis": "Consistency matters; watch for spread, pain, and scalp changes.",
        "seborrheic_dermatitis": "Keep the scalp/face routine simple and observe flaking trends.",
    }
    headline = headline_map.get(label, "Build a simple, steady routine and track how your skin responds.")
    today_focus = focus_map.get(label, "Stay consistent, introduce products slowly, and track change weekly.")
    if product_count:
        today_focus += f" You shortlisted {product_count} product{'s' if product_count != 1 else ''}, so introduce them one at a time."

    timeline = "Retake a clear photo in 7 days and compare trend. Consult a clinician if worsening, painful, spreading, or if you’re worried."
    return RoutinePlan(
        headline=headline,
        today_focus=today_focus,
        am=_uniq(am),
        pm=_uniq(pm),
        weekly=_uniq(weekly),
        avoid=_uniq(avoid),
        timeline=timeline,
        notes=_uniq(notes),
    )
