from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageOps

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
DEFAULT_MODEL_PATHS = [
    MODELS_DIR / "skin_model.keras",
    MODELS_DIR / "skin_model.h5",
]
LABELS_PATH = MODELS_DIR / "labels.json"

DEFAULT_LABELS = [
    "acne",
    "eczema",
    "rosacea",
    "psoriasis",
    "hyperpigmentation",
    "dryness",
    "seborrheic_dermatitis",
    "normal",
]


def _softmax(logits: np.ndarray) -> np.ndarray:
    logits = np.asarray(logits, dtype=np.float64)
    logits = logits - np.max(logits)
    exps = np.exp(logits)
    denom = np.sum(exps)
    if denom <= 0:
        return np.ones_like(exps) / len(exps)
    return exps / denom


def _top_k(probs: np.ndarray, labels: List[str], k: int = 3) -> List[Tuple[str, float]]:
    probs = np.asarray(probs, dtype=np.float64).reshape(-1)
    k = max(1, min(int(k), len(probs)))
    idx = np.argsort(-probs)[:k]
    return [(labels[i], float(probs[i])) for i in idx]


def load_labels() -> List[str]:
    if LABELS_PATH.exists():
        try:
            data = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("labels"), list):
                labels = [str(x) for x in data["labels"]]
                return labels or DEFAULT_LABELS
            if isinstance(data, list):
                labels = [str(x) for x in data]
                return labels or DEFAULT_LABELS
        except Exception:
            return DEFAULT_LABELS
    return DEFAULT_LABELS


def preprocess_image(pil_img: Image.Image, size: int = 224) -> np.ndarray:
    img = ImageOps.exif_transpose(pil_img)
    img = img.convert("RGB")
    img = ImageOps.fit(img, (size, size), method=Image.Resampling.LANCZOS)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return arr


class HeuristicModel:
    """
    Tiny baseline so the API works even without a trained model. Not medical.
    """

    def predict_proba(self, x: np.ndarray, labels: List[str]) -> np.ndarray:
        x = np.asarray(x, dtype=np.float32)
        r = x[:, :, 0]
        g = x[:, :, 1]
        b = x[:, :, 2]
        gray = 0.299 * r + 0.587 * g + 0.114 * b

        mean_rgb = np.array([r.mean(), g.mean(), b.mean()], dtype=np.float32)
        std_rgb = np.array([r.std(), g.std(), b.std()], dtype=np.float32)

        redness = float((mean_rgb[0] - (mean_rgb[1] + mean_rgb[2]) / 2.0))
        contrast = float(gray.std())

        gx = np.abs(gray[:, 1:] - gray[:, :-1])
        gy = np.abs(gray[1:, :] - gray[:-1, :])
        edge = float((gx.mean() + gy.mean()) / 2.0)

        saturation = float(std_rgb.mean())
        dryness_score = float((edge + contrast) - saturation * 0.5)

        label_set = {lbl: i for i, lbl in enumerate(labels)}
        logits = np.zeros((len(labels),), dtype=np.float64)

        def bump(label: str, value: float) -> None:
            if label in label_set:
                logits[label_set[label]] += float(value)

        bump("rosacea", redness * 4.0 + contrast * 1.0)
        bump("acne", contrast * 3.0 + edge * 2.0)
        bump("eczema", dryness_score * 3.0 + redness * 1.0)
        bump("psoriasis", dryness_score * 3.5 + contrast * 1.5)
        bump("dryness", dryness_score * 4.0)
        bump("hyperpigmentation", (mean_rgb.mean() * -1.0 + contrast * 1.0) * 2.0)
        bump("seborrheic_dermatitis", edge * 2.0 + redness * 1.0)
        bump("normal", -abs(redness) * 1.0 - contrast * 1.0 - edge * 1.0)

        logits = logits + 0.05
        return _softmax(logits)


def load_tf_model() -> Tuple[Optional[Any], str]:
    try:
        import tensorflow as tf  # type: ignore
    except Exception:
        return None, "TensorFlow not installed; using heuristic fallback."

    last_err: Optional[str] = None
    for p in DEFAULT_MODEL_PATHS:
        if p.exists():
            try:
                model = tf.keras.models.load_model(p)
                return model, f"Loaded model from {p.name}."
            except Exception as e:
                # If one candidate is corrupt/incompatible, try the next candidate.
                last_err = f"Found {p.name} but failed to load: {e}."
                continue
    if last_err:
        return None, f"{last_err} Using fallback."
    return None, "No trained model found; using heuristic fallback."


@dataclass
class Prediction:
    labels: List[str]
    probs: np.ndarray
    backend: str
    notes: str

    def top3(self) -> List[Tuple[str, float]]:
        return _top_k(self.probs, self.labels, k=3)


def predict(image_arr: np.ndarray, labels: List[str]) -> Prediction:
    model, note = load_tf_model()
    if model is not None:
        try:
            x = np.expand_dims(image_arr, axis=0).astype(np.float32)
            preds = np.asarray(model.predict(x, verbose=0)).reshape(-1)
            if preds.size != len(labels):
                labels = labels[: preds.size] if preds.size > 0 else labels
                preds = preds[: len(labels)]
            probs = preds.astype(np.float64)
            s = float(np.sum(probs)) if probs.size else 0.0
            if np.any(probs < 0) or (s != 0.0 and not math.isclose(s, 1.0, rel_tol=0.0, abs_tol=1e-2)):
                probs = _softmax(probs)
            return Prediction(labels=labels, probs=probs, backend="tensorflow", notes=note)
        except Exception as e:
            return Prediction(
                labels=labels,
                probs=HeuristicModel().predict_proba(image_arr, labels),
                backend="heuristic",
                notes=f"TF prediction failed ({e}); using fallback.",
            )

    return Prediction(
        labels=labels,
        probs=HeuristicModel().predict_proba(image_arr, labels),
        backend="heuristic",
        notes=note,
    )
