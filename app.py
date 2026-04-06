from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageOps

APP_TITLE = "Skin Photo Check (MVP)"
MODELS_DIR = Path("models")
DEFAULT_MODEL_PATHS = [
    MODELS_DIR / "skin_model.keras",
    MODELS_DIR / "skin_model.h5",
]
LABELS_PATH = MODELS_DIR / "labels.json"

PRODUCT_IMAGES_DIR = Path("assets") / "products"
PRODUCTS_CANDIDATES = [Path("products.json"), Path("product.json")]

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


def _safe_percent(p: float) -> str:
    p = float(p)
    p = 0.0 if math.isnan(p) else max(0.0, min(1.0, p))
    return f"{p * 100:.1f}%"


def _load_labels() -> List[str]:
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


@st.cache_data(show_spinner=False)
def load_products() -> Dict[str, Any]:
    for candidate in PRODUCTS_CANDIDATES:
        if candidate.exists():
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    return payload
            except Exception:
                break
    return {"version": 1, "products": [], "disclaimer": ""}


def _ensure_product_image(product_id: str, name: str) -> Path:
    """
    Creates a local placeholder product image so cards always show an image even without internet.
    """
    PRODUCT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = "".join(c for c in product_id.lower() if c.isalnum() or c in {"-", "_"}).strip("-_") or "product"
    path = PRODUCT_IMAGES_DIR / f"{safe_id}.png"
    if path.exists():
        return path

    img = Image.new("RGB", (900, 560), (246, 247, 251))
    # Simple two-tone band for a "modern" look.
    band = Image.new("RGB", (900, 220), (37, 99, 235))
    img.paste(band, (0, 0))

    try:
        from PIL import ImageDraw, ImageFont

        draw = ImageDraw.Draw(img)
        title = (name or "Product").strip()
        subtitle = "Recommended skincare (non-medical)"

        # Use default font (portable) to avoid extra dependencies.
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()

        draw.text((28, 22), title[:48], fill=(255, 255, 255), font=font_title)
        draw.text((28, 56), subtitle, fill=(226, 232, 240), font=font_sub)

        draw.rounded_rectangle((28, 260, 872, 520), radius=24, outline=(226, 232, 240), width=3, fill=(255, 255, 255))
        draw.text((48, 290), "Tap “Buy / View” to search this category.", fill=(17, 24, 39), font=font_sub)
        draw.text((48, 322), "Patch test first. Stop if irritation occurs.", fill=(75, 85, 99), font=font_sub)
    except Exception:
        pass

    img.save(path, format="PNG")
    return path


def _normalize_products(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensures every product has a local image path fallback so images render reliably.
    """
    items = payload.get("products", [])
    if not isinstance(items, list):
        return payload

    for item in items:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id", "")).strip() or str(item.get("name", "product")).strip()
        name = str(item.get("name", pid))
        # Prefer local image_path when present.
        image_path = str(item.get("image_path", "")).strip()
        if image_path:
            p = Path(image_path)
            if not p.exists():
                local_path = _ensure_product_image(pid, name)
                item["image_path"] = local_path.as_posix()
        else:
            local_path = _ensure_product_image(pid, name)
            item["image_path"] = local_path.as_posix()
    return payload


def filter_products(products_payload: Dict[str, Any], condition: str, limit: int = 6) -> List[Dict[str, Any]]:
    items = products_payload.get("products", [])
    if not isinstance(items, list):
        return []
    matches: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        conditions = item.get("conditions", [])
        if isinstance(conditions, list) and condition in {str(c) for c in conditions}:
            matches.append(item)
    return matches[: max(0, int(limit))]


def preprocess_image(pil_img: Image.Image, size: int = 224) -> np.ndarray:
    img = ImageOps.exif_transpose(pil_img)
    img = img.convert("RGB")
    img = ImageOps.fit(img, (size, size), method=Image.Resampling.LANCZOS)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return arr


@dataclass
class PredictionResult:
    labels: List[str]
    probs: np.ndarray
    backend: str
    notes: str = ""

    def top3(self) -> List[Tuple[str, float]]:
        return _top_k(self.probs, self.labels, k=3)


class HeuristicModel:
    """
    Tiny, dependency-light baseline model so the app runs even without a trained model.
    This is NOT a medical model; it only produces demo scores.
    """

    def predict_proba(self, x: np.ndarray, labels: List[str]) -> np.ndarray:
        # x: (H, W, 3) in [0,1]
        x = np.asarray(x, dtype=np.float32)
        h, w, _ = x.shape

        r = x[:, :, 0]
        g = x[:, :, 1]
        b = x[:, :, 2]
        gray = 0.299 * r + 0.587 * g + 0.114 * b

        mean_rgb = np.array([r.mean(), g.mean(), b.mean()], dtype=np.float32)
        std_rgb = np.array([r.std(), g.std(), b.std()], dtype=np.float32)

        # Very rough "redness" + "contrast" + "dryness-like texture" indicators
        redness = float((mean_rgb[0] - (mean_rgb[1] + mean_rgb[2]) / 2.0))
        contrast = float(gray.std())

        # Edge density via cheap gradient magnitude
        gx = np.abs(gray[:, 1:] - gray[:, :-1])
        gy = np.abs(gray[1:, :] - gray[:-1, :])
        edge = float((gx.mean() + gy.mean()) / 2.0)

        # Dryness proxy: high local contrast with lower saturation
        saturation = float(std_rgb.mean())
        dryness_score = float((edge + contrast) - saturation * 0.5)

        # Build label logits
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

        # Stabilize: always have some baseline mass
        logits = logits + 0.05
        return _softmax(logits)


@st.cache_resource(show_spinner=False)
def load_tf_model() -> Tuple[Optional[Any], str]:
    """
    Returns (model_or_none, note). TensorFlow is optional so the app still runs without it.
    """
    try:
        import tensorflow as tf  # type: ignore
    except Exception:
        return None, "TensorFlow not installed; using a lightweight heuristic fallback."

    for p in DEFAULT_MODEL_PATHS:
        if p.exists():
            try:
                model = tf.keras.models.load_model(p)
                return model, f"Loaded model from `{p.as_posix()}`."
            except Exception as e:
                return None, f"Found `{p.as_posix()}` but failed to load it: {e}. Falling back."
    return None, "No trained model found in `models/`; using a lightweight heuristic fallback."


def predict(image_arr: np.ndarray, labels: List[str]) -> PredictionResult:
    model, note = load_tf_model()
    if model is not None:
        try:
            # Assume a standard image model expecting (B,H,W,3) float input.
            x = np.expand_dims(image_arr, axis=0).astype(np.float32)
            preds = model.predict(x, verbose=0)
            preds = np.asarray(preds).reshape(-1)
            if preds.size != len(labels):
                # If labels mismatch, still show something sensible.
                labels = labels[: preds.size] if preds.size > 0 else labels
                preds = preds[: len(labels)]
            # If the model already outputs probabilities, this is mostly a no-op.
            probs = preds.astype(np.float64)
            if np.any(probs < 0) or not np.isclose(float(np.sum(probs)), 1.0, atol=1e-2):
                probs = _softmax(probs)
            return PredictionResult(labels=labels, probs=probs, backend="tensorflow", notes=note)
        except Exception as e:
            return PredictionResult(
                labels=labels,
                probs=HeuristicModel().predict_proba(image_arr, labels),
                backend="heuristic",
                notes=f"TF model prediction failed ({e}); using fallback.",
            )

    return PredictionResult(
        labels=labels,
        probs=HeuristicModel().predict_proba(image_arr, labels),
        backend="heuristic",
        notes=note,
    )


def render_product_cards(products: List[Dict[str, Any]]) -> None:
    if not products:
        st.caption("No product suggestions found for this label.")
        return

    cols = st.columns(3)
    for i, product in enumerate(products):
        col = cols[i % 3]
        with col:
            name = str(product.get("name", "Product"))
            reason = str(product.get("reason", ""))
            img_url = str(product.get("image_url", ""))
            img_path = str(product.get("image_path", "")).strip()

            if img_path and Path(img_path).exists():
                st.image(img_path, use_container_width=True)
            elif img_url:
                st.image(img_url, use_container_width=True)
            st.markdown(f"**{name}**")
            if reason:
                st.caption(reason)

            links = product_buy_links(product)
            if links:
                # Render up to 3 buttons per card.
                btn_cols = st.columns(min(3, len(links)))
                for j, (label, url) in enumerate(links[:3]):
                    with btn_cols[j]:
                        st.link_button(label, url, use_container_width=True)


def product_buy_links(product: Dict[str, Any]) -> List[Tuple[str, str]]:
    links: List[Tuple[str, str]] = []
    raw = product.get("buy_links")
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            url = str(item.get("url", "")).strip()
            if name and url:
                links.append((name, url))
    buy_url = str(product.get("buy_url", "")).strip()
    if not links and buy_url:
        links.append(("Buy / View", buy_url))
    return links


def label_title(label: str) -> str:
    return str(label).replace("_", " ").strip().title()


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


def render_recommendations(top_label: str, top_prob: float, top3: List[Tuple[str, float]], products_payload: Dict[str, Any]) -> None:
    st.subheader("Result (non-diagnostic)")

    st.markdown(
        f"""
        <div style="
          padding: 14px 14px;
          border-radius: 14px;
          border: 1px solid rgba(148,163,184,0.35);
          background: rgba(255,255,255,0.75);
          ">
          <div style="font-size: 1.05rem; font-weight: 700;">Possible condition: {label_title(top_label)}</div>
          <div style="color: rgba(17,24,39,0.75); margin-top: 6px;">Confidence: {_safe_percent(top_prob)} (for demo only)</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("**Top 3 possibilities**")
    for label, prob in top3:
        st.write(f"{label_title(label)} — {_safe_percent(prob)}")
        st.progress(min(1.0, max(0.0, float(prob))))

    st.divider()
    st.subheader("What you can do (safe, general)")
    for tip in advice_for_label(top_label):
        st.write(f"- {tip}")

    st.divider()
    st.subheader("Recommended products")
    suggested = filter_products(products_payload, top_label, limit=6)
    if not suggested:
        st.caption("No product suggestions found for this label.")
    else:
        # Image strip (like the mobile example)
        strip = suggested[:3]
        strip_cols = st.columns(len(strip))
        for i, p in enumerate(strip):
            with strip_cols[i]:
                img_path = str(p.get("image_path", "")).strip()
                img_url = str(p.get("image_url", "")).strip()
                if img_path and Path(img_path).exists():
                    st.image(img_path, use_container_width=True)
                elif img_url:
                    st.image(img_url, use_container_width=True)
                st.caption(str(p.get("name", "Product")))

        st.markdown("")
        for p in suggested:
            name = str(p.get("name", "Product"))
            reason = str(p.get("reason", "")).strip()
            st.markdown(f"**• {name}**")
            if reason:
                st.caption(f"→ {reason}")
            links = product_buy_links(p)
            if links:
                cols = st.columns(min(4, len(links)))
                for i, (lbl, url) in enumerate(links[:4]):
                    with cols[i]:
                        st.link_button(lbl, url, use_container_width=True)

    disclaimer = str(products_payload.get("disclaimer", "")).strip()
    if disclaimer:
        st.caption(disclaimer)


def render_cinematic_hero(reduce_motion: bool) -> None:
    """
    A "cinematic" hero section implemented with local HTML/CSS/JS (no paid APIs).
    Uses a lightweight canvas animation; gracefully degrades when Reduce motion is enabled.
    """
    if reduce_motion:
        st.markdown(
            '<div class="app-hero glass">'
            "<div class='section-title'>Upload or take a photo</div>"
            "<div class='muted'>Get top‑3 <b>non‑diagnostic</b> possibilities, confidence, and safe next steps.</div>"
            "<div style='margin-top:10px; display:flex; gap:10px; flex-wrap:wrap;'>"
            "<a href='#analyzer' style='text-decoration:none;'>"
            "<div style='display:inline-block; padding:10px 14px; border-radius:12px; background:#2563eb; color:white; font-weight:700;'>Start</div>"
            "</a>"
            "<div style='padding:10px 14px; border-radius:12px; background:rgba(15,23,42,0.06); border:1px solid rgba(148,163,184,0.35);'>"
            "Works offline (product images are local placeholders)</div>"
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    html = """
<div style="position:relative; border-radius:18px; overflow:hidden; border:1px solid rgba(148,163,184,0.35); box-shadow: 0 14px 40px rgba(15,23,42,0.10);">
  <canvas id="hero3d" style="display:block; width:100%; height:260px;"></canvas>
  <div style="position:absolute; inset:0; padding:18px 18px; display:flex; flex-direction:column; justify-content:center; pointer-events:none;">
    <div style="max-width:860px;">
      <div style="font-size:1.25rem; font-weight:850; color:#0f172a; letter-spacing:0.2px;">Cinematic skin check (3D MVP)</div>
      <div style="margin-top:6px; color:rgba(15,23,42,0.72); line-height:1.35;">
        Upload <b>or</b> take a photo. Get top‑3 <b>non‑diagnostic</b> possibilities, confidence, and product suggestions.
      </div>
      <div style="margin-top:12px; display:flex; gap:10px; flex-wrap:wrap; align-items:center; pointer-events:auto;">
        <a href="#analyzer" style="text-decoration:none;">
          <div style="display:inline-block; padding:10px 14px; border-radius:12px; background:#2563eb; color:white; font-weight:850;">
            Start
          </div>
        </a>
        <div style="padding:10px 14px; border-radius:12px; background:rgba(255,255,255,0.60); border:1px solid rgba(255,255,255,0.55); color:rgba(15,23,42,0.72);">
          Private on your device • Not medical advice
        </div>
      </div>
    </div>
  </div>

  <div style="position:absolute; top:14px; right:14px; display:flex; gap:8px; pointer-events:auto;">
    <button id="bottleBtn" style="cursor:pointer; border:1px solid rgba(255,255,255,0.55); background:rgba(255,255,255,0.55); color:#0f172a; padding:7px 10px; border-radius:999px; font-weight:800; font-size:12px;">Bottle</button>
    <button id="jarBtn" style="cursor:pointer; border:1px solid rgba(255,255,255,0.55); background:rgba(255,255,255,0.35); color:#0f172a; padding:7px 10px; border-radius:999px; font-weight:800; font-size:12px;">Jar</button>
  </div>
</div>

<script>
(() => {
  const canvas = document.getElementById("hero3d");
  const gl = canvas.getContext("webgl", { antialias: true, alpha: true, premultipliedAlpha: true });
  if (!gl) {
    // Fallback: paint a simple gradient if WebGL isn't available.
    const ctx = canvas.getContext("2d");
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.floor(rect.width));
    canvas.height = Math.max(1, Math.floor(rect.height));
    const g = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
    g.addColorStop(0, "rgba(37,99,235,0.22)");
    g.addColorStop(0.5, "rgba(99,102,241,0.16)");
    g.addColorStop(1, "rgba(16,185,129,0.14)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    return;
  }

  // Minimal mat4 helpers (column-major)
  const mat4 = {
    identity: () => [1,0,0,0,  0,1,0,0,  0,0,1,0,  0,0,0,1],
    multiply: (a,b) => {
      const o = new Array(16);
      for (let c=0; c<4; c++) {
        for (let r=0; r<4; r++) {
          o[c*4+r] =
            a[0*4+r]*b[c*4+0] +
            a[1*4+r]*b[c*4+1] +
            a[2*4+r]*b[c*4+2] +
            a[3*4+r]*b[c*4+3];
        }
      }
      return o;
    },
    perspective: (fovy, aspect, near, far) => {
      const f = 1.0 / Math.tan(fovy / 2);
      const nf = 1 / (near - far);
      return [
        f/aspect,0,0,0,
        0,f,0,0,
        0,0,(far+near)*nf,-1,
        0,0,(2*far*near)*nf,0
      ];
    },
    translate: (m, v) => {
      const [x,y,z] = v;
      const t = [1,0,0,0,  0,1,0,0,  0,0,1,0,  x,y,z,1];
      return mat4.multiply(m, t);
    },
    rotateY: (m, a) => {
      const c=Math.cos(a), s=Math.sin(a);
      const r=[ c,0,s,0,  0,1,0,0,  -s,0,c,0,  0,0,0,1];
      return mat4.multiply(m, r);
    },
    rotateX: (m, a) => {
      const c=Math.cos(a), s=Math.sin(a);
      const r=[ 1,0,0,0,  0,c,-s,0,  0,s,c,0,  0,0,0,1];
      return mat4.multiply(m, r);
    }
  };

  const vs = `
    attribute vec3 aPos;
    attribute vec3 aNor;
    uniform mat4 uMVP;
    uniform mat4 uModel;
    varying vec3 vNor;
    varying vec3 vPos;
    void main() {
      vec4 world = uModel * vec4(aPos, 1.0);
      vPos = world.xyz;
      vNor = mat3(uModel) * aNor;
      gl_Position = uMVP * vec4(aPos, 1.0);
    }
  `;

  const fs = `
    precision mediump float;
    varying vec3 vNor;
    varying vec3 vPos;
    uniform vec2 uRes;
    uniform float uTime;
    void main() {
      vec2 uv = gl_FragCoord.xy / uRes.xy;
      // Cinematic background gradient
      vec3 bgA = vec3(0.145, 0.388, 0.922); // blue
      vec3 bgB = vec3(0.388, 0.400, 0.945); // indigo
      vec3 bgC = vec3(0.063, 0.725, 0.506); // emerald
      float t = 0.5 + 0.5*sin(uTime*0.35 + uv.x*3.1415);
      vec3 bg = mix(mix(bgA, bgB, uv.y), bgC, 0.35*t);
      // Vignette
      vec2 p = uv - 0.5;
      float vig = smoothstep(0.75, 0.18, dot(p,p));
      bg *= (0.72 + 0.28*vig);

      // Lighting for the 3D object
      vec3 n = normalize(vNor);
      vec3 lightDir = normalize(vec3(0.6, 0.8, 0.4));
      float diff = max(dot(n, lightDir), 0.0);
      vec3 viewDir = normalize(vec3(0.0, 0.0, 1.2) - vPos);
      vec3 halfDir = normalize(lightDir + viewDir);
      float spec = pow(max(dot(n, halfDir), 0.0), 64.0);

      // "Glass" material tint + cinematic fresnel + label band
      vec3 tint = vec3(0.95, 0.98, 1.0);
      float fres = pow(1.0 - max(dot(n, viewDir), 0.0), 3.0);
      vec3 rim = vec3(0.35, 0.55, 1.0) * (0.45 + 0.55*fres);

      // Subtle "label" band around mid section
      float band = smoothstep(-0.05, 0.05, sin((vPos.y + 0.15) * 7.0));
      vec3 labelCol = mix(vec3(0.20, 0.25, 0.34), vec3(0.92, 0.95, 1.0), 0.55);
      vec3 baseCol = tint * (0.18 + 0.82*diff) + 0.70*spec + rim;
      vec3 col = mix(baseCol, baseCol * (0.78 + 0.22*labelCol), 0.18 * band);

      // Mix with background for a translucent feel
      vec3 outCol = mix(bg, col, 0.82);
      gl_FragColor = vec4(outCol, 1.0);
    }
  `;

  function compile(type, src) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.warn(gl.getShaderInfoLog(s));
      gl.deleteShader(s);
      return null;
    }
    return s;
  }
  function link(vsSrc, fsSrc) {
    const v = compile(gl.VERTEX_SHADER, vsSrc);
    const f = compile(gl.FRAGMENT_SHADER, fsSrc);
    if (!v || !f) return null;
    const p = gl.createProgram();
    gl.attachShader(p, v);
    gl.attachShader(p, f);
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
      console.warn(gl.getProgramInfoLog(p));
      return null;
    }
    return p;
  }

  const prog = link(vs, fs);
  if (!prog) return;
  gl.useProgram(prog);

  function normalize3(x,y,z) {
    const l = Math.hypot(x,y,z) || 1;
    return [x/l, y/l, z/l];
  }

  function latheMesh(profile, segments) {
    // profile: [[radius, y], ...] from bottom to top
    const verts = [];
    const segs = Math.max(18, Math.min(96, segments|0));
    const n = profile.length;

    // Precompute 2D normals for each profile point in (r,y)
    const nr = new Array(n);
    const ny = new Array(n);
    for (let i=0; i<n; i++) {
      const p0 = profile[Math.max(0, i-1)];
      const p1 = profile[Math.min(n-1, i+1)];
      const dr = p1[0] - p0[0];
      const dy = p1[1] - p0[1];
      // Perpendicular to tangent (dr,dy) is (dy, -dr)
      const nn = normalize3(dy, -dr, 0);
      nr[i] = nn[0];
      ny[i] = nn[1];
    }

    function pushVert(r, y, theta, nRad, nY) {
      const c = Math.cos(theta), s = Math.sin(theta);
      const x = r * c;
      const z = r * s;
      const nx = nRad * c;
      const nz = nRad * s;
      const nn = normalize3(nx, nY, nz);
      verts.push(x, y, z, nn[0], nn[1], nn[2]);
    }

    for (let si=0; si<segs; si++) {
      const t0 = (si / segs) * Math.PI * 2;
      const t1 = ((si + 1) / segs) * Math.PI * 2;
      for (let pi=0; pi<n-1; pi++) {
        const r00 = profile[pi][0], y00 = profile[pi][1];
        const r01 = profile[pi+1][0], y01 = profile[pi+1][1];
        const n0r = nr[pi], n0y = ny[pi];
        const n1r = nr[pi+1], n1y = ny[pi+1];

        // Quad (t0,t1) x (pi,pi+1) -> 2 triangles
        pushVert(r00, y00, t0, n0r, n0y);
        pushVert(r01, y01, t0, n1r, n1y);
        pushVert(r01, y01, t1, n1r, n1y);

        pushVert(r00, y00, t0, n0r, n0y);
        pushVert(r01, y01, t1, n1r, n1y);
        pushVert(r00, y00, t1, n0r, n0y);
      }
    }

    // Caps (top and bottom discs) for a more "product" look
    const rBot = profile[0][0], yBot = profile[0][1];
    const rTop = profile[n-1][0], yTop = profile[n-1][1];
    for (let si=0; si<segs; si++) {
      const t0 = (si / segs) * Math.PI * 2;
      const t1 = ((si + 1) / segs) * Math.PI * 2;
      // bottom
      verts.push(0, yBot, 0, 0, -1, 0);
      verts.push(rBot*Math.cos(t1), yBot, rBot*Math.sin(t1), 0, -1, 0);
      verts.push(rBot*Math.cos(t0), yBot, rBot*Math.sin(t0), 0, -1, 0);
      // top
      verts.push(0, yTop, 0, 0, 1, 0);
      verts.push(rTop*Math.cos(t0), yTop, rTop*Math.sin(t0), 0, 1, 0);
      verts.push(rTop*Math.cos(t1), yTop, rTop*Math.sin(t1), 0, 1, 0);
    }

    return new Float32Array(verts);
  }

  const bottleProfile = [
    [0.46, -1.20],
    [0.52, -1.05],
    [0.56, -0.65],
    [0.56,  0.10],
    [0.48,  0.48],
    [0.30,  0.70],
    [0.22,  0.95],
    [0.24,  1.18]
  ];

  const jarProfile = [
    [0.62, -1.15],
    [0.66, -0.95],
    [0.70, -0.30],
    [0.70,  0.45],
    [0.66,  0.75],
    [0.64,  0.98],
    [0.68,  1.12]
  ];

  let current = "bottle";
  let mesh = latheMesh(bottleProfile, 72);

  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, mesh, gl.STATIC_DRAW);

  const aPos = gl.getAttribLocation(prog, "aPos");
  const aNor = gl.getAttribLocation(prog, "aNor");
  gl.enableVertexAttribArray(aPos);
  gl.enableVertexAttribArray(aNor);
  gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 24, 0);
  gl.vertexAttribPointer(aNor, 3, gl.FLOAT, false, 24, 12);

  const uMVP = gl.getUniformLocation(prog, "uMVP");
  const uModel = gl.getUniformLocation(prog, "uModel");
  const uRes = gl.getUniformLocation(prog, "uRes");
  const uTime = gl.getUniformLocation(prog, "uTime");

  let w=0, h=0, dpr=Math.max(1, Math.min(2, window.devicePixelRatio || 1));
  function resize() {
    const rect = canvas.getBoundingClientRect();
    w = Math.max(1, Math.floor(rect.width));
    h = Math.max(1, Math.floor(rect.height));
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    gl.viewport(0, 0, canvas.width, canvas.height);
  }
  resize();
  window.addEventListener("resize", resize);

  gl.enable(gl.DEPTH_TEST);
  gl.clearColor(0,0,0,0);

  function setActiveButtons() {
    const b = document.getElementById("bottleBtn");
    const j = document.getElementById("jarBtn");
    if (!b || !j) return;
    if (current === "bottle") {
      b.style.background = "rgba(255,255,255,0.55)";
      j.style.background = "rgba(255,255,255,0.35)";
    } else {
      b.style.background = "rgba(255,255,255,0.35)";
      j.style.background = "rgba(255,255,255,0.55)";
    }
  }

  function setMesh(kind) {
    current = kind;
    mesh = latheMesh(kind === "jar" ? jarProfile : bottleProfile, 72);
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, mesh, gl.STATIC_DRAW);
    setActiveButtons();
  }

  const bottleBtn = document.getElementById("bottleBtn");
  const jarBtn = document.getElementById("jarBtn");
  if (bottleBtn) bottleBtn.addEventListener("click", () => setMesh("bottle"));
  if (jarBtn) jarBtn.addEventListener("click", () => setMesh("jar"));
  setActiveButtons();

  const start = performance.now();
  function draw(now) {
    const t = (now - start) * 0.001;
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.uniform2f(uRes, canvas.width, canvas.height);
    gl.uniform1f(uTime, t);

    const aspect = w / Math.max(1, h);
    const proj = mat4.perspective(0.9, aspect, 0.1, 20.0);
    let model = mat4.identity();
    model = mat4.translate(model, [0, Math.sin(t*0.8)*0.06, -4.4]);
    model = mat4.rotateY(model, t * 0.45);
    model = mat4.rotateX(model, 0.55 + Math.sin(t*0.6)*0.06);
    const mvp = mat4.multiply(proj, model);

    gl.uniformMatrix4fv(uMVP, false, new Float32Array(mvp));
    gl.uniformMatrix4fv(uModel, false, new Float32Array(model));

    gl.drawArrays(gl.TRIANGLES, 0, mesh.length / 6);
    requestAnimationFrame(draw);
  }

  // NOTE: Streamlit passes no flags into the iframe, so we always animate here.
  requestAnimationFrame(draw);
})();
</script>
"""
    components.html(html, height=280)


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="🧴", layout="wide")

    if "reduce_motion" not in st.session_state:
        st.session_state.reduce_motion = False

    with st.sidebar:
        st.markdown("### Settings")
        st.session_state.reduce_motion = st.toggle("Reduce motion", value=bool(st.session_state.reduce_motion))
        st.caption("Tip: If animations feel heavy, enable Reduce motion.")

    st.markdown(
        """
        <style>
          /* Animated soft background */
          @keyframes bgmove {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
          }
          .stApp {
            background: linear-gradient(120deg, rgba(37,99,235,0.08), rgba(16,185,129,0.06), rgba(99,102,241,0.06));
            background-size: 200% 200%;
            animation: bgmove 10s ease-in-out infinite;
          }
          .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1100px; }
          [data-testid="stMetricValue"] { font-size: 1.6rem; }
          /* Subtle animated header glow */
          @keyframes glow {
            0% { filter: drop-shadow(0 6px 18px rgba(37,99,235,0.20)); }
            50% { filter: drop-shadow(0 10px 28px rgba(37,99,235,0.34)); }
            100% { filter: drop-shadow(0 6px 18px rgba(37,99,235,0.20)); }
          }
          .app-hero {
            border-radius: 18px;
            padding: 18px 18px;
            background: linear-gradient(90deg, rgba(37,99,235,0.12), rgba(99,102,241,0.10), rgba(16,185,129,0.08));
            border: 1px solid rgba(148,163,184,0.35);
            animation: glow 4s ease-in-out infinite;
          }
          .glass {
            border-radius: 18px;
            border: 1px solid rgba(148,163,184,0.35);
            background: rgba(255,255,255,0.72);
            box-shadow: 0 14px 40px rgba(15,23,42,0.08);
          }
          .section-title {
            font-size: 1.1rem;
            font-weight: 750;
            margin: 0.2rem 0 0.6rem 0;
          }
          .muted { color: rgba(17,24,39,0.70); }

          /* Reduce motion support */
          @media (prefers-reduced-motion: reduce) {
            .stApp { animation: none !important; }
            .app-hero { animation: none !important; }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title(APP_TITLE)
    render_cinematic_hero(reduce_motion=bool(st.session_state.reduce_motion))

    with st.expander("Safety & limitations (read first)", expanded=True):
        st.warning(
            "This tool is an educational MVP and **not a medical diagnosis**. "
            "If you have severe pain, swelling, fever, spreading rash, rapid changes, bleeding, "
            "or if you're worried, seek a licensed clinician promptly."
        )
        st.caption(
            "Lighting, camera quality, skin tone, and image angle can change results. "
            "Always patch-test new products and stop if irritation occurs."
        )

    labels = _load_labels()
    products_payload = _normalize_products(load_products())

    left, right = st.columns([1, 1])
    with left:
        st.markdown('<div id="analyzer"></div>', unsafe_allow_html=True)
        st.markdown("### Analyzer")
        tab_upload, tab_camera = st.tabs(["Upload", "Camera"])
        img: Optional[Image.Image] = None
        with tab_upload:
            uploaded = st.file_uploader("Upload a skin photo (JPG/PNG)", type=["jpg", "jpeg", "png"])
            if uploaded is not None:
                img = Image.open(uploaded)
                st.image(img, caption="Selected image", use_container_width=True)

        with tab_camera:
            cam = st.camera_input("Take a photo")
            if cam is not None:
                img = Image.open(cam)
                st.image(img, caption="Captured image", use_container_width=True)

        analyze = st.button("Analyze", type="primary", disabled=img is None, use_container_width=True)

    with right:
        st.markdown("### Output")
        if img is None:
            st.info("Upload an image or take a photo to see predictions and product suggestions.")
            return

        if not analyze:
            st.caption("Click **Analyze** when ready.")
            return

        with st.spinner("Analyzing..."):
            image_arr = preprocess_image(img)
            result = predict(image_arr, labels=labels)

        top3 = result.top3()
        top_label, top_prob = top3[0]

        st.caption(result.notes)
        render_recommendations(top_label, top_prob, top3, products_payload)

    with st.expander("Developer info"):
        st.code(
            json.dumps(
                {
                    "model_paths_checked": [p.as_posix() for p in DEFAULT_MODEL_PATHS],
                    "labels_path": LABELS_PATH.as_posix(),
                    "products_paths_checked": [p.as_posix() for p in PRODUCTS_CANDIDATES],
                },
                indent=2,
            ),
            language="json",
        )


if __name__ == "__main__":
    main()
