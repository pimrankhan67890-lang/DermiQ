from __future__ import annotations

from typing import Dict, List


def advice_for_label(label: str) -> List[str]:
    tips: Dict[str, List[str]] = {
        "acne": [
            "Wash gently 1–2x/day (avoid harsh scrubbing).",
            "Avoid squeezing/picking pimples.",
            "Use non-comedogenic moisturizer + sunscreen daily.",
            "Start new actives slowly; patch test first.",
        ],
        "rosacea": [
            "Use fragrance-free cleanser and moisturizer.",
            "Avoid known triggers (heat, spicy food, alcohol) if they affect you.",
            "Prefer mineral sunscreen; avoid stinging products.",
            "If frequent flushing or burning, consider a clinician.",
        ],
        "eczema": [
            "Moisturize often (especially after bathing).",
            "Use gentle, fragrance-free products; avoid hot showers.",
            "Stop new products if they burn or itch more.",
            "If cracks/oozing or severe itch, consider a clinician.",
        ],
        "psoriasis": [
            "Moisturize to reduce dryness and scaling.",
            "Avoid picking scales.",
            "If thick plaques, pain, or joint symptoms, consider a clinician.",
        ],
        "hyperpigmentation": [
            "Use sunscreen daily (helps prevent dark spots from worsening).",
            "Avoid picking/scratching spots.",
            "Introduce brightening actives slowly; patch test.",
        ],
        "dryness": [
            "Use a gentle cleanser and a thicker moisturizer.",
            "Limit very hot showers; moisturize right after.",
            "Avoid over-exfoliating and strong actives until comfortable.",
        ],
        "seborrheic_dermatitis": [
            "If scalp is involved, consider an anti-dandruff shampoo routine.",
            "Avoid heavy fragranced products that irritate.",
            "If worsening redness or pain, consider a clinician.",
        ],
        "normal": [
            "Keep a simple routine: gentle cleanse, moisturize, sunscreen.",
            "Patch test new products and introduce one at a time.",
        ],
    }
    return tips.get(label, ["Keep a gentle routine; patch test new products; seek care if worsening."])

