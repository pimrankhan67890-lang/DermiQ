from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image, ImageOps

from backend.quality import check_image_quality


def _to_rgb(pil_img: Image.Image) -> Image.Image:
    return ImageOps.exif_transpose(pil_img).convert("RGB")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def decode_upload(raw: bytes) -> Image.Image:
    return _to_rgb(Image.open(BytesIO(raw)))


def capture_guidance(pil_img: Image.Image) -> Dict[str, Any]:
    img = _to_rgb(pil_img)
    w, h = img.size
    quality = check_image_quality(img)
    centered = abs((w / max(h, 1)) - 1.0) < 0.55
    close_enough = min(w, h) >= 300
    stability = "stable" if quality.ok and centered and close_enough else "adjust"
    tips: List[str] = []
    if not close_enough:
        tips.append("Move the camera closer so the skin area fills more of the frame.")
    if not centered:
        tips.append("Center the target skin area and keep only one main region in frame.")
    if not quality.ok:
        tips.append(str(quality.message or "Retake the photo with steadier framing and better lighting."))
    if not tips:
        tips.append("Frame looks good. Hold steady and capture the same area next time for comparison.")
    return {
        "ready": bool(quality.ok),
        "stability": stability,
        "target_fill": "good" if close_enough else "too_far",
        "frame_balance": "centered" if centered else "off_center",
        "quality": quality.metrics,
        "tips": tips[:3],
    }


def compare_captures(current_img: Image.Image, baseline_img: Optional[Image.Image]) -> Dict[str, Any]:
    current = _to_rgb(current_img)
    if baseline_img is None:
        return {
            "available": False,
            "summary": "No baseline image available yet. Capture one clear scan first, then compare your next photo against it.",
            "change_score": 0.0,
            "framing_match": "unknown",
        }

    baseline = _to_rgb(baseline_img)
    size = (192, 192)
    cur = np.asarray(current.resize(size, Image.Resampling.BILINEAR), dtype=np.float32) / 255.0
    base = np.asarray(baseline.resize(size, Image.Resampling.BILINEAR), dtype=np.float32) / 255.0

    diff = np.abs(cur - base)
    change_score = float(np.mean(diff))
    framing_delta = abs((current.size[0] / max(current.size[1], 1)) - (baseline.size[0] / max(baseline.size[1], 1)))
    framing_match = "good" if framing_delta < 0.12 else ("ok" if framing_delta < 0.25 else "poor")

    if change_score < 0.035:
        summary = "This area looks broadly similar to the baseline capture."
    elif change_score < 0.08:
        summary = "There is a visible change versus the baseline. Compare redness, texture, and size carefully."
    else:
        summary = "This capture looks meaningfully different from the baseline. Recheck symptoms and consider whether the area is worsening."

    return {
        "available": True,
        "summary": summary,
        "change_score": round(change_score, 4),
        "framing_match": framing_match,
    }


def build_reasoning_summary(
    *,
    top_label: str,
    confidence_mode: str,
    top_prob: float,
    symptoms: Dict[str, Any],
    case_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    case_state = case_state or {}
    symptom_list = symptoms.get("symptoms") if isinstance(symptoms.get("symptoms"), list) else []
    triggers = symptoms.get("triggers") if isinstance(symptoms.get("triggers"), list) else []
    duration_days = int(_safe_float(symptoms.get("duration_days"), 0))
    severity = _safe_float(symptoms.get("severity"), 0.0)
    supporting: List[str] = []

    if top_label and top_label != "uncertain":
        supporting.append(f"Visual model currently leans toward {top_label.replace('_', ' ')}.")
    supporting.append(f"Confidence mode is {confidence_mode}.")
    if severity:
        supporting.append(f"Reported severity is {severity:.1f}/10.")
    if duration_days:
        supporting.append(f"Duration reported: about {duration_days} day{'s' if duration_days != 1 else ''}.")
    if symptom_list:
        supporting.append("Current symptoms: " + ", ".join(str(x) for x in symptom_list[:4]) + ".")
    if triggers:
        supporting.append("Possible triggers: " + ", ".join(str(x) for x in triggers[:4]) + ".")
    if str(case_state.get("response_trend") or "") == "worsening":
        supporting.append("Your saved journey suggests recent worsening.")
    elif str(case_state.get("response_trend") or "") == "improving":
        supporting.append("Your saved journey suggests some improvement.")
    if case_state.get("irritation_flags"):
        supporting.append("At least one tracked product was marked as irritating.")

    if not supporting:
        supporting.append("DermIQ is using the current image plus your saved journey to stay conservative.")

    what_changed = "No prior journey trend available yet."
    trend = str(case_state.get("response_trend") or "unknown")
    if trend == "improving":
        what_changed = "Compared with recent check-ins, your skin trend looks more stable or slightly improved."
    elif trend == "worsening":
        what_changed = "Compared with recent check-ins, the trend looks worse, so the protocol should stay conservative."
    elif trend == "steady":
        what_changed = "Compared with recent check-ins, the skin looks broadly steady without a clear improvement signal."

    return {
        "likely_focus": top_label,
        "confidence_mode": confidence_mode,
        "supporting_factors": supporting[:5],
        "what_changed": what_changed,
        "severity": severity,
        "duration_days": duration_days,
        "top_prob": round(float(top_prob or 0.0), 4),
    }
