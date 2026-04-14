from __future__ import annotations

from typing import Any, Dict, List, Tuple


LABEL_TO_FAMILY: Dict[str, str] = {
    "acne": "acneiform",
    "rosacea": "vascular_inflammatory",
    "eczema": "eczematous_dermatitis",
    "dryness": "eczematous_dermatitis",
    "psoriasis": "papulosquamous",
    "hyperpigmentation": "pigmentary",
    "melasma": "pigmentary",
    "post_inflammatory_hyperpigmentation": "pigmentary",
    "seborrheic_dermatitis": "scalp_hair_related",
    "tinea": "fungal_infectious_looking",
    "tinea_corporis": "fungal_infectious_looking",
    "tinea_pedis": "fungal_infectious_looking",
    "tinea_versicolor": "fungal_infectious_looking",
    "folliculitis": "acneiform",
    "vitiligo": "pigmentary",
    "wart_like": "growth_lesion_suspicious",
    "molluscum": "growth_lesion_suspicious",
    "suspicious_lesion": "growth_lesion_suspicious",
    "unclear_other": "normal_low_concern_unclear",
    "normal": "normal_low_concern_unclear",
}


FAMILY_DISPLAY: Dict[str, str] = {
    "acneiform": "acneiform",
    "eczematous_dermatitis": "eczematous / dermatitis",
    "papulosquamous": "papulosquamous",
    "pigmentary": "pigmentary",
    "fungal_infectious_looking": "fungal / infectious-looking",
    "scalp_hair_related": "scalp / hair-related",
    "growth_lesion_suspicious": "growth / lesion / suspicious",
    "vascular_inflammatory": "vascular / inflammatory red lesion",
    "normal_low_concern_unclear": "normal / low-concern / unclear",
    "urgent_escalate": "urgent / escalate",
}


RED_FLAG_KEYWORDS = {
    "bleeding",
    "rapidly changing",
    "rapid_change",
    "severe_pain",
    "spreading",
    "spreading_fast",
    "eye_involvement",
    "fever",
}


def family_for_label(label: str) -> str:
    key = str(label or "").strip().lower()
    if not key:
        return "normal_low_concern_unclear"
    return LABEL_TO_FAMILY.get(key, "normal_low_concern_unclear")


def aggregate_family_scores(top3: List[Dict[str, Any]]) -> List[Tuple[str, float]]:
    scores: Dict[str, float] = {}
    for item in top3 or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip().lower()
        try:
            prob = float(item.get("prob", 0.0) or 0.0)
        except Exception:
            prob = 0.0
        family = family_for_label(label)
        scores[family] = scores.get(family, 0.0) + max(0.0, prob)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


def confidence_mode_for_prediction(
    *,
    top_label: str,
    top_prob: float,
    second_prob: float,
    red_flags: List[str] | None = None,
) -> Tuple[str, bool]:
    red_flags = [str(x).strip().lower() for x in (red_flags or []) if str(x).strip()]
    if red_flags:
        return "escalate", True
    margin = float(top_prob) - float(second_prob)
    label = str(top_label or "").strip().lower()
    family = family_for_label(label)
    if family == "growth_lesion_suspicious":
        return "escalate", True
    if float(top_prob) >= 0.78 and margin >= 0.18:
        return "confident", False
    if float(top_prob) >= 0.55 and margin >= 0.08:
        return "watch", False
    return "uncertain", True


def body_zone_normalized(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    mappings = {
        "forehead": "face",
        "cheek": "face",
        "chin": "face",
        "nose": "face",
        "jaw": "face",
        "scalp": "scalp",
        "hairline": "scalp",
        "neck": "neck",
        "chest": "trunk",
        "back": "trunk",
        "abdomen": "trunk",
        "arm": "arms",
        "hand": "hands",
        "finger": "hands",
        "leg": "legs",
        "thigh": "legs",
        "knee": "legs",
        "foot": "feet",
        "toe": "feet",
        "nail": "feet",
    }
    for key, mapped in mappings.items():
        if key in raw:
            return mapped
    return raw.replace(" ", "_")


def family_reasoning_copy(family: str) -> str:
    return {
        "acneiform": "DermIQ is seeing an acneiform pattern, so it should prioritize pore-friendly support and gentle actives.",
        "eczematous_dermatitis": "DermIQ is seeing a dermatitis-like pattern, so barrier protection matters more than aggressive treatment.",
        "papulosquamous": "DermIQ is seeing a scaling or plaque-like pattern, so the plan should stay conservative and watch spread carefully.",
        "pigmentary": "DermIQ is seeing a pigmentary pattern, so sunscreen and low-irritation routine choices matter most.",
        "fungal_infectious_looking": "DermIQ is seeing a possible fungal or infectious-looking pattern, so routine advice should stay conservative and escalation should remain visible.",
        "scalp_hair_related": "DermIQ is seeing a scalp or hair-related pattern, so scalp-friendly care and consistency matter more than stacking products.",
        "growth_lesion_suspicious": "DermIQ is seeing a lesion-like pattern, so it should avoid commerce-first behavior and favor clinician review.",
        "vascular_inflammatory": "DermIQ is seeing an inflammatory or redness-led pattern, so triggers, barrier care, and calming choices matter most.",
        "normal_low_concern_unclear": "DermIQ does not have a strong pattern match yet, so it should stay minimal and ask for a clearer retake.",
        "urgent_escalate": "DermIQ is seeing signals that should keep the advice conservative and push escalation.",
    }.get(family, "DermIQ is using a conservative family-level interpretation while it waits for a clearer signal.")
