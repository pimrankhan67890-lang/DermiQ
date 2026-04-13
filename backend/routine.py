from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RoutinePlan:
    headline: str
    today_focus: str
    protocol_stage: str
    confidence_mode: str
    am: List[str]
    pm: List[str]
    weekly: List[str]
    avoid: List[str]
    timeline: str
    when_to_rescan: str
    when_to_consult: str
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _uniq(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in items:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def build_routine_plan(
    *,
    top_label: str,
    selected_products: List[Dict[str, Any]],
    prefs: Optional[Dict[str, Any]] = None,
    case_state: Optional[Dict[str, Any]] = None,
) -> RoutinePlan:
    label = str(top_label or "").strip().lower()
    prefs = prefs or {}
    case_state = case_state or {}

    sensitive = bool(prefs.get("sensitive_skin", False))
    fragrance_free = bool(prefs.get("fragrance_free", True))
    pregnancy_safe = bool(prefs.get("pregnancy_safe", False))
    note = str(prefs.get("note", "")).strip()
    preferred_store = str(prefs.get("preferred_store", "")).strip()

    confidence_mode = str(case_state.get("confidence_mode") or "uncertain").strip().lower()
    response_trend = str(case_state.get("response_trend") or "unknown").strip().lower()
    symptom_severity = float(case_state.get("symptom_severity") or 0.0)
    irritation_flags = case_state.get("irritation_flags") if isinstance(case_state.get("irritation_flags"), list) else []
    active_products = int(case_state.get("products_in_use") or 0)
    helped_products = int(case_state.get("helped_products") or 0)
    inconsistent_products = int(case_state.get("inconsistent_products") or 0)

    categories = {str(item.get("category", "")).strip().lower() for item in selected_products if isinstance(item, dict)}
    has_cleanser = "cleanser" in categories
    has_moisturizer = "moisturizer" in categories
    has_sunscreen = "sunscreen" in categories
    has_treatment = "treatment" in categories
    product_count = len([item for item in selected_products if isinstance(item, dict)])

    am: List[str] = []
    pm: List[str] = []
    weekly: List[str] = []
    avoid: List[str] = []
    notes: List[str] = []

    am.append("Cleanse gently with lukewarm water.") if has_cleanser else am.append("Rinse and cleanse gently only if needed.")
    am.append("Moisturize with a thin barrier-supporting layer.") if has_moisturizer else am.append("Moisturize if skin feels tight or dry.")
    am.append("Apply sunscreen SPF 30+ and reapply when outdoors.") if has_sunscreen else am.append("If outdoors, use a sunscreen SPF 30+.")

    pm.append("Cleanse gently to remove sunscreen, sweat, or makeup.") if has_cleanser else pm.append("Cleanse gently in the evening.")
    if has_treatment:
        pm.append("Apply the selected treatment slowly: start 2 to 3 nights per week, then increase only if tolerated.")
    pm.append("Finish with moisturizer to support the skin barrier.") if has_moisturizer else pm.append("Moisturize after cleansing if needed.")

    weekly.append("Take one progress photo weekly in the same lighting and angle.")
    weekly.append("Introduce only one new product at a time and observe for 5 to 7 days.")

    if fragrance_free:
        avoid.append("Avoid strongly fragranced products if you notice stinging, redness, or itching.")
    if sensitive:
        avoid.append("Avoid introducing multiple new products in the same week.")
        notes.append("Sensitive-skin mode is on, so slow introductions matter more than aggressive treatment.")

    if label == "acne":
        notes.append("Acne often improves slowly, so give routine changes 6 to 8 weeks unless irritation appears.")
        avoid.append("Avoid picking, harsh scrubs, or over-drying the skin.")
    elif label == "rosacea":
        notes.append("Track common rosacea triggers like heat, sun, stress, alcohol, and spicy food.")
        avoid.append("Avoid harsh exfoliants or anything that causes stinging.")
    elif label in {"eczema", "dryness"}:
        notes.append("Barrier repair matters most here, so consistency is better than adding more actives.")
        avoid.append("Avoid long hot showers and stop anything that burns or worsens the rash.")
    elif label == "hyperpigmentation":
        notes.append("Daily sunscreen is the most important step for hyperpigmentation and tone changes.")
        avoid.append("Avoid aggressive scrubs or over-exfoliating darker marks.")
    elif label == "psoriasis":
        notes.append("If scaling is widespread, painful, or worsening, clinician confirmation is a safer next step.")
    elif label == "seborrheic_dermatitis":
        notes.append("Keep scalp and face care simple and track whether flaking is improving week to week.")

    if pregnancy_safe:
        notes.append("Pregnancy-safe preference is on, so avoid starting strong actives unless a clinician approves.")
        avoid.append("Avoid retinoids unless a clinician specifically approves them.")

    if preferred_store:
        notes.append(f"Preferred store selected: {preferred_store}. Compare formulas carefully before buying.")
    if note:
        notes.append(f"User note: {note}")

    if active_products:
        notes.append(f"You currently have {active_products} tracked product{'s' if active_products != 1 else ''} in use.")
    if helped_products:
        notes.append(f"{helped_products} tracked product{'s are' if helped_products != 1 else ' is'} already marked as helping.")
    if irritation_flags:
        notes.append("Potentially irritating products: " + ", ".join(str(x) for x in irritation_flags[:3]) + ".")
    if inconsistent_products:
        notes.append("Use has looked inconsistent, so keep this protocol simple for one full week before judging results.")

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
        "psoriasis": "Consistency matters, and any pain or fast spread should raise caution.",
        "seborrheic_dermatitis": "Keep the scalp and face routine simple and observe flaking trends.",
    }

    headline = headline_map.get(label, "Build a simple, steady routine and track how your skin responds.")
    today_focus = focus_map.get(label, "Stay consistent, introduce products slowly, and track change weekly.")
    if product_count:
        today_focus += f" You shortlisted {product_count} product{'s' if product_count != 1 else ''}, so introduce them one at a time."

    if confidence_mode == "watch":
        today_focus += " DermIQ is watching for a clearer trend, so keep this week conservative."
    elif confidence_mode == "uncertain":
        today_focus = "DermIQ is not confident yet, so keep your routine minimal, retake a clearer photo, and avoid stacking new actives."
    elif confidence_mode == "escalate":
        today_focus = "Pause experimentation, keep the barrier routine gentle, and prioritize clinician follow-up."

    if response_trend == "worsening":
        today_focus += " Your recent check-ins look worse, so do not add extra products this week."
    elif response_trend == "improving":
        today_focus += " Your recent trend looks better, so consistency matters more than changing the plan."

    if symptom_severity >= 7:
        avoid.append("Avoid stronger actives until severity settles or a clinician guides the next step.")

    protocol_stage = "starting"
    if response_trend == "improving":
        protocol_stage = "stabilizing"
    elif response_trend == "worsening":
        protocol_stage = "adjusting"
    elif active_products >= 2 or helped_products:
        protocol_stage = "tracking"
    if confidence_mode == "escalate":
        protocol_stage = "escalate"

    when_to_rescan = "Retake a clear close-up in 7 days using the same lighting and angle."
    if confidence_mode == "uncertain":
        when_to_rescan = "Retake a clearer close-up in natural light within 2 to 3 days before changing too much."
    elif response_trend == "worsening":
        when_to_rescan = "Retake a clear close-up in 3 to 5 days so DermIQ can check whether the trend is still worsening."

    when_to_consult = "Consult a clinician if symptoms are painful, spreading, bleeding, involve the eyes, or you feel worried."
    if confidence_mode == "escalate" or symptom_severity >= 8:
        when_to_consult = "Consult a clinician promptly now instead of trying more products."
    elif response_trend == "worsening" or irritation_flags:
        when_to_consult = "Consult a clinician if the next weekly check-in still looks worse or irritation continues after stopping the suspected product."

    timeline = f"{when_to_rescan} {when_to_consult}"
    return RoutinePlan(
        headline=headline,
        today_focus=today_focus,
        protocol_stage=protocol_stage,
        confidence_mode=confidence_mode,
        am=_uniq(am),
        pm=_uniq(pm),
        weekly=_uniq(weekly),
        avoid=_uniq(avoid),
        timeline=timeline,
        when_to_rescan=when_to_rescan,
        when_to_consult=when_to_consult,
        notes=_uniq(notes),
    )
