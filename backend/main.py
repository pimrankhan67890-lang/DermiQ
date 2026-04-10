from __future__ import annotations

import os
import json
import logging
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from backend.advice import advice_for_label
from backend.products import filter_products_for_top3, load_products, public_product
from backend.security import InMemoryRateLimiter, RateLimit
from backend.quality import check_image_quality
from backend.skin_infer import load_labels, load_tf_model, predict_pil
from backend.tracker import assess_escalation, add_event, create_session, delete_session, get_events

app = FastAPI(title="Skin Check API", version="0.1.0")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dermiq")

_rate_limiter = InMemoryRateLimiter()
_predict_rate = RateLimit(
    max_requests=int(os.getenv("PREDICT_RATE_MAX", "30")),
    window_seconds=int(os.getenv("PREDICT_RATE_WINDOW_SECONDS", "600")),
)
_max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))  # 10MB
_max_image_pixels = int(os.getenv("MAX_IMAGE_PIXELS", str(12_000_000)))  # ~12 MP
_landing_dir = Path(__file__).resolve().parent.parent / "landing"
_landing_index = _landing_dir / "index.html"
_enable_telemetry = str(os.getenv("ENABLE_TELEMETRY", "0")).strip() in {"1", "true", "yes", "on"}


def _cors_allow_origins() -> List[str]:
    raw = str(os.getenv("CORS_ALLOW_ORIGINS", "*")).strip()
    if not raw or raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


# Allow local dev from Next.js (and easy hosting). Tighten via CORS_ALLOW_ORIGINS for production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
    return resp


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/model")
def model_status() -> Dict[str, Any]:
    """
    Lightweight status endpoint for debugging deployments.
    """
    labels = load_labels()
    model, note = load_tf_model()
    return {
        "model_loaded": bool(model is not None),
        "model_backend": "tensorflow" if model is not None else "heuristic",
        "notes": note,
        "labels": labels,
    }


@app.post("/events")
async def events(payload: Dict[str, Any]) -> Dict[str, str]:
    """
    Optional lightweight telemetry endpoint.

    - Disabled by default. Enable with ENABLE_TELEMETRY=1.
    - Logs to stdout (Render captures logs).
    - Do not send images or sensitive content.
    """
    if _enable_telemetry:
        try:
            logger.info("event=%s", json.dumps(payload, ensure_ascii=False)[:2000])
        except Exception:
            logger.info("event=<unserializable>")
    return {"status": "ok"}


@app.post("/feedback")
async def feedback(payload: Dict[str, Any]) -> Dict[str, str]:
    """
    Optional feedback endpoint for improving product/model quality.

    - Disabled by default. Enable with ENABLE_TELEMETRY=1.
    - Logs to stdout (Render captures logs).
    """
    if _enable_telemetry:
        try:
            logger.info("feedback=%s", json.dumps(payload, ensure_ascii=False)[:2000])
        except Exception:
            logger.info("feedback=<unserializable>")
    return {"status": "ok"}


@app.post("/tracker/session")
async def tracker_session() -> Dict[str, str]:
    return {"session_id": create_session()}


@app.post("/tracker/event")
async def tracker_event(payload: Dict[str, Any]) -> Dict[str, str]:
    sid = str(payload.get("session_id", "")).strip()
    kind = str(payload.get("kind", "")).strip()
    data = payload.get("payload", {})
    if not isinstance(data, dict):
        data = {"value": data}
    ts = payload.get("ts")
    try:
        ts_i = int(ts) if ts is not None else None
    except Exception:
        ts_i = None
    add_event(sid, kind, data, ts=ts_i)
    return {"status": "ok"}


@app.get("/tracker/timeline")
async def tracker_timeline(session_id: str, limit: int = 200) -> Dict[str, Any]:
    events = get_events(session_id, limit=limit)
    esc = assess_escalation(events)
    return {
        "events": events,
        "escalation": {"should_consult": esc.should_consult, "reason": esc.reason, "level": esc.level},
    }


@app.post("/tracker/delete")
async def tracker_delete(payload: Dict[str, Any]) -> Dict[str, str]:
    sid = str(payload.get("session_id", "")).strip()
    delete_session(sid)
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root():
    if _landing_index.exists():
        return FileResponse(str(_landing_index))
    return {"status": "ok"}


@app.post("/predict")
async def predict_endpoint(request: Request, file: UploadFile = File(...)) -> Dict[str, Any]:
    scan_id = uuid.uuid4().hex
    ip = request.client.host if request.client else ""
    if not _rate_limiter.allow(f"predict:{ip}", _predict_rate):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file.")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty upload.")
    if len(raw) > _max_upload_bytes:
        raise HTTPException(status_code=413, detail="Upload too large.")

    try:
        pil_img = Image.open(BytesIO(raw))
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read image.")

    try:
        w, h = pil_img.size
        if int(w) * int(h) > _max_image_pixels:
            raise HTTPException(status_code=413, detail="Image resolution too large.")
    except Exception:
        # If size info is unavailable, continue; Pillow will still validate decode during processing.
        pass

    # Quick, safety-first image quality gate (prevents garbage results).
    q = check_image_quality(pil_img)
    if not q.ok:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "image_quality",
                "reason": q.code,
                "message": q.message,
                "metrics": q.metrics,
            },
        )

    labels = load_labels()
    result = predict_pil(pil_img, labels=labels)
    top3 = result.top3()
    top_label, top_prob = top3[0]

    products_payload = load_products()
    top3_payload = [{"label": lbl, "prob": float(prob)} for lbl, prob in top3]
    products = [public_product(p) for p in filter_products_for_top3(products_payload, top3_payload, limit=6)]

    response: Dict[str, Any] = {
        "scan_id": scan_id,
        "top_label": top_label,
        "top_prob": float(top_prob),
        "top3": [{"label": lbl, "prob": float(prob)} for lbl, prob in top3],
        "advice": advice_for_label(top_label),
        "products": products,
        "disclaimer": str(products_payload.get("disclaimer", "")).strip(),
        "model_backend": result.backend,
        "notes": result.notes,
        "safety": (
            "This tool is not a medical diagnosis. If you have severe pain, swelling, fever, spreading rash, "
            "rapid changes, bleeding, or you are worried, seek a licensed clinician promptly."
        ),
    }

    # If the client supplies a tracker session id, store analysis event (no image bytes stored).
    sid = str(request.headers.get("X-Session-Id", "")).strip()
    if sid:
        try:
            add_event(
                sid,
                "analysis",
                {
                    "top_label": top_label,
                    "top_prob": float(top_prob),
                    "top3": [{"label": lbl, "prob": float(prob)} for lbl, prob in top3],
                    "model_backend": result.backend,
                    "product_ids": [p.get("id") for p in products if isinstance(p, dict)],
                    "scan_id": scan_id,
                },
            )
        except Exception:
            pass
    return response


# Serve the cinematic landing site from the same origin so local preview is a single URL:
# - Open http://127.0.0.1:8000 to see the website
# - API remains available at /health and /predict
if _landing_dir.exists():
    app.mount("/", StaticFiles(directory=str(_landing_dir), html=True), name="site")
