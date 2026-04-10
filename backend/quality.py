from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageOps


@dataclass(frozen=True)
class QualityResult:
    ok: bool
    code: str
    message: str
    metrics: dict


def _to_rgb(pil_img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(pil_img)
    return img.convert("RGB")


def _laplacian_variance(gray: np.ndarray) -> float:
    """
    gray: float32 array in range 0..1, shape (H, W)
    Uses 4-neighbor Laplacian. Returns variance.
    """
    g = np.asarray(gray, dtype=np.float32)
    if g.ndim != 2 or min(g.shape[0], g.shape[1]) < 5:
        return 0.0
    c = g[1:-1, 1:-1]
    lap = -4.0 * c + g[1:-1, :-2] + g[1:-1, 2:] + g[:-2, 1:-1] + g[2:, 1:-1]
    return float(np.var(lap))


def check_image_quality(
    pil_img: Image.Image,
    *,
    min_side_px: int = 160,
    downsample_px: int = 256,
    min_brightness: float = 0.18,
    max_brightness: float = 0.98,
    min_lap_var: float = 0.0018,
) -> QualityResult:
    """
    Very fast, non-ML quality gate.

    Rejects:
    - too small
    - too dark / too bright
    - too blurry (low Laplacian variance)

    Thresholds are intentionally conservative to reduce false rejects.
    """
    img = _to_rgb(pil_img)
    w, h = img.size
    if min(w, h) < int(min_side_px):
        return QualityResult(
            ok=False,
            code="too_small",
            message=f"Image is too small. Use a closer photo (min {min_side_px}px on the shortest side).",
            metrics={"w": int(w), "h": int(h)},
        )

    # Downsample for cheap metrics.
    ds = int(downsample_px)
    if ds > 0:
        scale = ds / float(max(w, h))
        if scale < 1.0:
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.BILINEAR)

    arr = np.asarray(img, dtype=np.float32) / 255.0
    if arr.ndim != 3 or arr.shape[2] != 3:
        return QualityResult(ok=False, code="bad_image", message="Invalid image.", metrics={})

    gray = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    brightness = float(np.mean(gray)) if gray.size else 0.0
    if brightness < float(min_brightness):
        return QualityResult(
            ok=False,
            code="too_dark",
            message="Photo is too dark. Move to better lighting and try again.",
            metrics={"brightness": brightness},
        )
    if brightness > float(max_brightness):
        return QualityResult(
            ok=False,
            code="too_bright",
            message="Photo is too bright/overexposed. Avoid direct glare and try again.",
            metrics={"brightness": brightness},
        )

    lap_var = _laplacian_variance(gray)
    if lap_var < float(min_lap_var):
        return QualityResult(
            ok=False,
            code="too_blurry",
            message="Photo looks too blurry. Hold steady and make sure the skin area is in focus.",
            metrics={"lap_var": lap_var},
        )

    return QualityResult(ok=True, code="ok", message="", metrics={"brightness": brightness, "lap_var": lap_var})

