from __future__ import annotations

import os
import json
import logging
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from backend.advice import advice_for_label
from backend.affiliate import affiliate_url
from backend.auth import exchange_supabase_token, get_supabase_config
from backend.billing import (
    create_manual_pro_for_session,
    get_billing_status,
    link_session_to_pro_token,
    stripe_create_checkout_url,
    stripe_handle_webhook,
)
from backend.capture import build_reasoning_summary, capture_guidance, compare_captures
from backend.products import filter_products_for_top3, list_products, load_products, public_product
from backend.outgoing import normalize_store, validate_outgoing_url
from backend.routine import build_routine_plan
from backend.security import InMemoryRateLimiter, RateLimit
from backend.quality import check_image_quality
from backend.skin_infer import load_labels, load_tf_model, predict_pil
from backend.tracker import (
    assess_escalation,
    assess_user_escalation,
    add_event,
    create_session,
    delete_session,
    delete_user_data,
    get_analytics_summary,
    get_daily_scans,
    get_events,
    get_journey_summary,
    get_profile,
    get_user_id_for_session,
    incr_daily_scans,
    link_session_to_user,
    list_tracked_products,
    list_user_scans,
    save_feedback_record,
    save_follow_up_record,
    save_routine_plan_record,
    save_scan_record,
    save_tracked_products,
    update_tracked_product_status,
    upsert_profile,
)

app = FastAPI(title="Skin Check API", version="0.1.0")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dermiq")

_rate_limiter = InMemoryRateLimiter()
_predict_rate = RateLimit(
    max_requests=int(os.getenv("PREDICT_RATE_MAX", "30")),
    window_seconds=int(os.getenv("PREDICT_RATE_WINDOW_SECONDS", "600")),
)
_freemium_daily_max = int(os.getenv("FREEMIUM_DAILY_MAX", "3"))
_min_confidence = float(os.getenv("MIN_CONFIDENCE", "0.0"))
_max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))  # 10MB
_max_image_pixels = int(os.getenv("MAX_IMAGE_PIXELS", str(12_000_000)))  # ~12 MP
_landing_dir = Path(__file__).resolve().parent.parent / "landing"
_landing_index = _landing_dir / "index.html"
_landing_journey = _landing_dir / "journey.html"
_landing_agent = _landing_dir / "agent.html"
_enable_telemetry = str(os.getenv("ENABLE_TELEMETRY", "0")).strip() in {"1", "true", "yes", "on"}
_consult_url = str(os.getenv("CONSULT_URL", "")).strip()
_consult_label = str(os.getenv("CONSULT_LABEL", "Consult a clinician")).strip()
_analytics_key = str(os.getenv("DERMIQ_ANALYTICS_KEY", "")).strip()


def _cors_allow_origins() -> List[str]:
    raw = str(os.getenv("CORS_ALLOW_ORIGINS", "*")).strip()
    if not raw or raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def _session_id(request: Request) -> str:
    return str(request.headers.get("X-Session-Id", "")).strip()


def _current_user(request: Request) -> Dict[str, Any]:
    sid = _session_id(request)
    if not sid:
        return {}
    user_id = get_user_id_for_session(sid)
    if not user_id:
        return {}
    profile = get_profile(user_id)
    if not profile:
        return {}
    return profile


def _require_user(request: Request) -> Dict[str, Any]:
    profile = _current_user(request)
    if not profile:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return profile


def _parse_capture_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    symptoms = payload.get("symptoms", [])
    triggers = payload.get("triggers", [])
    if not isinstance(symptoms, list):
        symptoms = []
    if not isinstance(triggers, list):
        triggers = []
    return {
        "duration_days": int(float(payload.get("duration_days", 0) or 0)),
        "severity": float(payload.get("severity", 0) or 0),
        "symptoms": [str(x).strip() for x in symptoms if str(x).strip()][:6],
        "triggers": [str(x).strip() for x in triggers if str(x).strip()][:6],
        "body_zone": str(payload.get("body_zone", "")).strip(),
    }


def _predict_image_response(
    *,
    pil_img: Image.Image,
    scan_id: str,
    sid: str,
    plan: str,
    capture_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    labels = load_labels()
    result = predict_pil(pil_img, labels=labels)
    top3 = result.top3()
    top_label, top_prob = top3[0]
    if _min_confidence > 0 and float(top_prob) < float(_min_confidence):
        top_label = "uncertain"

    products_payload = load_products()
    top3_payload = [{"label": lbl, "prob": float(prob)} for lbl, prob in top3]
    products = [public_product(p) for p in filter_products_for_top3(products_payload, top3_payload, limit=6)] if top_label != "uncertain" else []
    affiliate_disclosure = str(products_payload.get("affiliate_disclosure", "")).strip()
    amazon_required = str(os.getenv("DERMIQ_AMAZON_DISCLOSURE", "")).strip()
    affiliate_line = " ".join([x for x in [affiliate_disclosure, amazon_required] if x])

    confidence_mode = "uncertain" if top_label == "uncertain" else ("watch" if float(top_prob) < 0.7 else "confident")
    case_state: Dict[str, Any] = {}
    user_id = get_user_id_for_session(sid) if sid else ""
    if user_id:
        try:
            journey = get_journey_summary(user_id)
            case_state = journey.get("case_state", {}) if isinstance(journey, dict) else {}
        except Exception:
            case_state = {}

    reasoning = build_reasoning_summary(
        top_label=top_label,
        confidence_mode=confidence_mode,
        top_prob=float(top_prob),
        symptoms=capture_context or {},
        case_state=case_state,
    )

    response: Dict[str, Any] = {
        "scan_id": scan_id,
        "top_label": top_label,
        "top_prob": float(top_prob),
        "confidence_mode": confidence_mode,
        "top3": [{"label": lbl, "prob": float(prob)} for lbl, prob in top3],
        "advice": (
            [
                "Result uncertain. Retake a clear, close-up photo in natural light.",
                "If symptoms are severe, spreading, painful, bleeding, rapidly changing, or you’re worried, consult a licensed clinician promptly.",
            ]
            if top_label == "uncertain"
            else advice_for_label(top_label)
        ),
        "products": products,
        "disclaimer": str(products_payload.get("disclaimer", "")).strip(),
        "affiliate_disclosure": affiliate_line,
        "model_backend": result.backend,
        "notes": result.notes,
        "case_state": case_state,
        "reasoning": reasoning,
        "capture_guidance": capture_guidance(pil_img),
        "safety": (
            "This tool is not a medical diagnosis. If you have severe pain, swelling, fever, spreading rash, "
            "rapid changes, bleeding, or you are worried, seek a licensed clinician promptly."
        ),
    }

    if sid:
        try:
            new_used = incr_daily_scans(sid)
            response["usage"] = {
                "plan": plan,
                "daily_max": _freemium_daily_max if plan != "pro" else None,
                "daily_used": new_used,
                "daily_remaining": (
                    max(0, int(_freemium_daily_max) - int(new_used))
                    if (_freemium_daily_max > 0 and plan != "pro")
                    else None
                ),
            }
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
                    "capture_context": capture_context or {},
                    "confidence_mode": confidence_mode,
                },
            )
            if user_id:
                save_scan_record(
                    user_id=user_id,
                    scan_id=scan_id,
                    session_id=sid,
                    top_label=top_label,
                    top_prob=float(top_prob),
                    top3=response["top3"],
                    backend=result.backend,
                )
            events = get_events(sid, limit=200)
            esc = assess_escalation(events)
            response["escalation"] = {
                "should_consult": bool(esc.should_consult),
                "reason": str(esc.reason or ""),
                "level": str(esc.level or "none"),
                "consult_url": _consult_url,
                "consult_label": _consult_label,
            }
        except Exception:
            pass

    return response


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


@app.get("/auth/config")
def auth_config() -> Dict[str, Any]:
    cfg = get_supabase_config()
    return {
        "enabled": bool(cfg.get("enabled")),
        "url": str(cfg.get("url") or ""),
        "anon_key": str(cfg.get("anon_key") or ""),
        "google_enabled": bool(cfg.get("google_enabled")),
    }


@app.post("/auth/session/exchange")
async def auth_session_exchange(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
    sid = _session_id(request) or str(payload.get("session_id", "")).strip()
    if not sid:
        raise HTTPException(status_code=400, detail="Missing session.")
    token = str(payload.get("access_token", "")).strip()
    profile, err = exchange_supabase_token(token)
    if err:
        raise HTTPException(status_code=400, detail=err)
    user_id = str(profile.get("user_id", "")).strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="Could not resolve user.")
    upsert_profile(
        user_id,
        email=str(profile.get("email", "")),
        full_name=str(profile.get("full_name", "")),
        avatar_url=str(profile.get("avatar_url", "")),
        provider=str(profile.get("provider", "supabase")),
    )
    link_session_to_user(sid, user_id)
    add_event(sid, "auth_linked", {"user_id": user_id, "provider": str(profile.get("provider", "supabase"))})
    return {"status": "ok", "user": get_profile(user_id), "journey": get_journey_summary(user_id)}


@app.get("/products")
def products_catalog(category: str = "", limit: int = 100) -> Dict[str, Any]:
    """
    Public product catalog for the landing UI (no prices).
    """
    payload = load_products()
    items = [public_product(p) for p in list_products(payload, category=category, limit=limit)]
    affiliate_disclosure = str(payload.get("affiliate_disclosure", "")).strip()
    amazon_required = str(os.getenv("DERMIQ_AMAZON_DISCLOSURE", "")).strip()
    affiliate_line = " ".join([x for x in [affiliate_disclosure, amazon_required] if x])
    return {
        "products": items,
        "disclaimer": str(payload.get("disclaimer", "")).strip(),
        "affiliate_disclosure": affiliate_line,
    }


@app.get("/out")
async def outbound_redirect(
    request: Request,
    url: str,
    store: str = "",
    product_id: str = "",
    scan_id: str = "",
    session_id: str = "",
) -> RedirectResponse:
    """
    Internal redirect for affiliate + click tracking.

    - Validates allowed host
    - Logs click event (tracker DB if session id exists; stdout telemetry optional)
    - Redirects (302) to the final affiliate-tagged URL
    """
    chk = validate_outgoing_url(url)
    if not chk.ok:
        raise HTTPException(status_code=400, detail=f"Invalid outbound link ({chk.reason}).")

    store_name = normalize_store(store, chk.host)
    final_url = affiliate_url(store_name, url)

    sid = str(request.headers.get("X-Session-Id", "")).strip() or str(session_id or "").strip()
    click = {
        "store": store_name,
        "product_id": str(product_id or "").strip(),
        "scan_id": str(scan_id or "").strip(),
        "host": chk.host,
    }
    if sid:
        try:
            add_event(sid, "product_click", click)
        except Exception:
            pass
    if _enable_telemetry:
        try:
            logger.info("event=%s", json.dumps({"kind": "product_click", **click}, ensure_ascii=False)[:2000])
        except Exception:
            pass

    return RedirectResponse(url=final_url, status_code=302)


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
    session_id = str(payload.get("session_id", "")).strip()
    user_id = get_user_id_for_session(session_id) if session_id else ""
    try:
        save_feedback_record(
            user_id=user_id,
            session_id=session_id,
            scan_id=str(payload.get("scan_id", "")).strip(),
            rating=int(payload.get("rating", 0) or 0),
            accurate_label=str(payload.get("accurate_label", "")).strip(),
            notes=str(payload.get("note", "")).strip(),
        )
    except Exception:
        pass
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


@app.get("/analytics/summary")
async def analytics_summary(
    request: Request,
    days: int = 30,
    session_id: str = "",
    admin_key: str = "",
) -> Dict[str, Any]:
    supplied_key = str(admin_key or request.headers.get("X-Analytics-Key", "")).strip()
    if _analytics_key and supplied_key == _analytics_key:
        return get_analytics_summary(days=days, session_id="")

    sid = str(session_id or request.headers.get("X-Session-Id", "")).strip()
    if not sid:
        raise HTTPException(status_code=403, detail="Analytics key required.")
    return get_analytics_summary(days=days, session_id=sid)


@app.get("/case/state")
async def case_state(request: Request) -> Dict[str, Any]:
    profile = _require_user(request)
    data = get_journey_summary(str(profile.get("user_id", "")))
    esc = data.get("escalation") if isinstance(data.get("escalation"), dict) else {}
    state = data.get("case_state") if isinstance(data.get("case_state"), dict) else {}
    return {
        "case_state": {
            **state,
            "consult_url": _consult_url,
            "consult_label": _consult_label,
        },
        "progress_signal": data.get("progress_signal", {}),
        "escalation": {
            **esc,
            "consult_url": _consult_url,
            "consult_label": _consult_label,
        },
    }


@app.post("/case/check-in")
async def case_check_in(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
    return await journey_follow_up(request, payload)


@app.get("/progress/compare")
async def progress_compare(request: Request) -> Dict[str, Any]:
    profile = _require_user(request)
    data = get_journey_summary(str(profile.get("user_id", "")))
    scans = data.get("recent_scans") if isinstance(data.get("recent_scans"), list) else []
    case_state = data.get("case_state") if isinstance(data.get("case_state"), dict) else {}
    latest = scans[0] if scans else {}
    previous = scans[1] if len(scans) > 1 else {}
    latest_prob = float(latest.get("top_prob", 0.0) or 0.0)
    previous_prob = float(previous.get("top_prob", 0.0) or 0.0)
    confidence_delta = round(latest_prob - previous_prob, 4) if previous else 0.0
    summary = "No prior comparison available yet."
    trend = str(case_state.get("response_trend") or "unknown")
    if trend == "improving":
        summary = "Recent follow-ups suggest improvement compared with earlier check-ins."
    elif trend == "worsening":
        summary = "Recent follow-ups suggest worsening, so the protocol should stay conservative."
    elif previous:
        summary = "Comparison uses your latest two scans plus current follow-up trend."
    return {
        "summary": summary,
        "latest_scan": latest,
        "previous_scan": previous,
        "confidence_delta": confidence_delta,
        "case_state": case_state,
    }


@app.get("/escalation/recommendation")
async def escalation_recommendation(request: Request) -> Dict[str, Any]:
    profile = _require_user(request)
    esc = assess_user_escalation(str(profile.get("user_id", "")))
    return {
        **esc,
        "consult_url": _consult_url,
        "consult_label": _consult_label,
    }


@app.get("/journey/summary")
async def journey_summary(request: Request) -> Dict[str, Any]:
    profile = _require_user(request)
    data = get_journey_summary(str(profile.get("user_id", "")))
    esc = data.get("escalation") if isinstance(data.get("escalation"), dict) else {}
    data["escalation"] = {
        **esc,
        "consult_url": _consult_url,
        "consult_label": _consult_label,
    }
    case_state = data.get("case_state") if isinstance(data.get("case_state"), dict) else {}
    if case_state:
        case_state["consult_url"] = _consult_url
        case_state["consult_label"] = _consult_label
        data["case_state"] = case_state
    return data


@app.get("/journey/scans")
async def journey_scans(request: Request, limit: int = 24) -> Dict[str, Any]:
    profile = _require_user(request)
    return {"scans": list_user_scans(str(profile.get("user_id", "")), limit=limit)}


@app.post("/journey/product-track")
async def journey_product_track(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
    profile = _require_user(request)
    user_id = str(profile.get("user_id", ""))
    selected_ids = payload.get("selected_products", [])
    if not isinstance(selected_ids, list):
        selected_ids = []
    scan_id = str(payload.get("scan_id", "")).strip()
    prefs = payload.get("preferences", {})
    if not isinstance(prefs, dict):
        prefs = {}

    products_payload = load_products()
    products_list = products_payload.get("products", [])
    if not isinstance(products_list, list):
        products_list = []
    wanted = {str(x).strip() for x in selected_ids if str(x).strip()}
    selected_products = []
    for p in products_list:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id", "")).strip()
        if pid and pid in wanted:
            selected_products.append(public_product(p))

    items = save_tracked_products(
        user_id,
        selected_products,
        scan_id=scan_id,
        default_status=str(payload.get("status", "planned")).strip() or "planned",
        preferred_store=str(prefs.get("preferred_store", "")).strip(),
        notes=str(prefs.get("note", "")).strip(),
    )
    return {"status": "ok", "products": items}


@app.post("/journey/product-status")
async def journey_product_status(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
    profile = _require_user(request)
    item = update_tracked_product_status(
        str(profile.get("user_id", "")),
        str(payload.get("product_id", "")).strip(),
        str(payload.get("status", "planned")).strip() or "planned",
        notes=str(payload.get("notes", "")).strip(),
    )
    if not item:
        raise HTTPException(status_code=404, detail="Tracked product not found.")
    return {"status": "ok", "product": item}


@app.post("/journey/routine/save")
async def journey_routine_save(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
    profile = _require_user(request)
    plan = payload.get("plan", {})
    if not isinstance(plan, dict):
        raise HTTPException(status_code=400, detail="Invalid plan.")
    saved = save_routine_plan_record(
        str(profile.get("user_id", "")),
        str(payload.get("scan_id", "")).strip(),
        str(payload.get("top_label", "")).strip(),
        plan,
    )
    return {"status": "ok", "routine": saved}


@app.post("/journey/follow-up")
async def journey_follow_up(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
    profile = _require_user(request)
    flags = payload.get("flags", {})
    if not isinstance(flags, dict):
        flags = {}
    item = save_follow_up_record(
        str(profile.get("user_id", "")),
        severity=float(payload.get("severity", 0) or 0),
        notes=str(payload.get("notes", "")).strip(),
        flags=flags,
        scan_id=str(payload.get("scan_id", "")).strip(),
    )
    esc = assess_user_escalation(str(profile.get("user_id", "")))
    esc["consult_url"] = _consult_url
    esc["consult_label"] = _consult_label
    return {"status": "ok", "follow_up": item, "escalation": esc}


@app.get("/journey/escalation")
async def journey_escalation(request: Request) -> Dict[str, Any]:
    profile = _require_user(request)
    esc = assess_user_escalation(str(profile.get("user_id", "")))
    esc["consult_url"] = _consult_url
    esc["consult_label"] = _consult_label
    return esc


@app.post("/journey/delete")
async def journey_delete(request: Request) -> Dict[str, str]:
    profile = _require_user(request)
    delete_user_data(str(profile.get("user_id", "")))
    return {"status": "ok"}


@app.post("/routine/plan")
async def routine_plan(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate an educational daily routine plan from selected products.
    """
    sid = str(request.headers.get("X-Session-Id", "")).strip()
    scan_id = str(payload.get("scan_id", "")).strip()
    top_label = str(payload.get("top_label", "")).strip()
    selected_ids = payload.get("selected_products", [])
    if not isinstance(selected_ids, list):
        selected_ids = []

    prefs = payload.get("preferences", {})
    if not isinstance(prefs, dict):
        prefs = {}

    products_payload = load_products()
    products_list = products_payload.get("products", [])
    if not isinstance(products_list, list):
        products_list = []

    wanted = {str(x).strip() for x in selected_ids if str(x).strip()}
    selected_products = []
    for p in products_list:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id", "")).strip()
        if pid and pid in wanted:
            selected_products.append(public_product(p))

    case_state: Dict[str, Any] = {}
    user_id = get_user_id_for_session(sid) if sid else ""
    if user_id:
        try:
            journey = get_journey_summary(user_id)
            case_state = journey.get("case_state", {}) if isinstance(journey, dict) else {}
        except Exception:
            case_state = {}

    plan = build_routine_plan(top_label=top_label, selected_products=selected_products, prefs=prefs, case_state=case_state)

    if sid:
        try:
            add_event(
                sid,
                "routine_generated",
                {
                    "scan_id": scan_id,
                    "top_label": top_label,
                    "selected_products": [p.get("id") for p in selected_products],
                    "preferences": prefs,
                },
            )
        except Exception:
            pass

    return {
        "scan_id": scan_id,
        "top_label": top_label,
        "selected_products": selected_products,
        "plan": plan.to_dict(),
        "case_state": case_state,
        "safety": (
            "Educational only — not a medical diagnosis. Stop products if irritation occurs. "
            "Seek a licensed clinician promptly for severe pain, swelling, fever, spreading rash, bleeding, "
            "rapid changes, or if you are worried."
        ),
    }


@app.post("/protocol/generate")
async def protocol_generate(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
    return await routine_plan(request, payload)


@app.get("/billing/status")
async def billing_status(request: Request) -> Dict[str, Any]:
    sid = str(request.headers.get("X-Session-Id", "")).strip()
    st = get_billing_status(sid)
    return {"plan": st.plan, "pro_token": st.pro_token if st.plan == "pro" else ""}


@app.post("/billing/link")
async def billing_link(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
    sid = str(request.headers.get("X-Session-Id", "")).strip()
    tok = str(payload.get("pro_token", "")).strip()
    ok = link_session_to_pro_token(sid, tok)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid Pro code.")
    if sid:
        try:
            add_event(sid, "pro_linked", {"source": "code"})
        except Exception:
            pass
    st = get_billing_status(sid)
    return {"status": "ok", "plan": st.plan}


@app.post("/billing/unlock")
async def billing_unlock(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Manual unlock helper (optional).

    Set DERMIQ_PRO_MASTER_CODE to a secret string, then call this endpoint with:
      {"master_code": "..."}

    This creates a Pro token and links it to the current session (useful before Stripe is configured).
    """
    master = str(os.getenv("DERMIQ_PRO_MASTER_CODE", "")).strip()
    if not master:
        raise HTTPException(status_code=501, detail="Manual unlock not enabled.")
    if str(payload.get("master_code", "")).strip() != master:
        raise HTTPException(status_code=403, detail="Invalid code.")
    sid = str(request.headers.get("X-Session-Id", "")).strip()
    tok = create_manual_pro_for_session(sid)
    if not tok:
        raise HTTPException(status_code=400, detail="Missing session.")
    if sid:
        try:
            add_event(sid, "pro_linked", {"source": "manual_unlock"})
        except Exception:
            pass
    return {"status": "ok", "plan": "pro", "pro_token": tok}


@app.post("/billing/checkout")
async def billing_checkout(request: Request) -> Dict[str, Any]:
    sid = str(request.headers.get("X-Session-Id", "")).strip()
    if sid:
        try:
            add_event(sid, "billing_checkout_started", {"provider": "stripe"})
        except Exception:
            pass
    url, err = stripe_create_checkout_url(sid)
    if not url:
        raise HTTPException(status_code=501, detail=err or "Billing not available.")
    return {"url": url}


@app.post("/billing/webhook/stripe")
async def billing_webhook_stripe(request: Request) -> Dict[str, Any]:
    raw = await request.body()
    sig = str(request.headers.get("Stripe-Signature", "")).strip()
    ok, msg = stripe_handle_webhook(raw, sig)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@app.get("/", include_in_schema=False)
def root():
    if _landing_index.exists():
        return FileResponse(str(_landing_index))
    return {"status": "ok"}


@app.get("/journey", include_in_schema=False)
def journey_page():
    if _landing_journey.exists():
        return FileResponse(str(_landing_journey))
    raise HTTPException(status_code=404, detail="Journey page not found.")


@app.get("/agent", include_in_schema=False)
def agent_page():
    if _landing_agent.exists():
        return FileResponse(str(_landing_agent))
    raise HTTPException(status_code=404, detail="Agent page not found.")


@app.post("/capture/analyze")
async def capture_analyze(
    request: Request,
    file: UploadFile = File(...),
    duration_days: int = Form(0),
    severity: float = Form(0),
    symptoms: str = Form(""),
    triggers: str = Form(""),
    body_zone: str = Form(""),
) -> Dict[str, Any]:
    sid = str(request.headers.get("X-Session-Id", "")).strip()
    plan = "free"
    if sid:
        try:
            plan = get_billing_status(sid).plan
        except Exception:
            plan = "free"

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty upload.")
    try:
        pil_img = Image.open(BytesIO(raw))
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read image.")

    q = check_image_quality(pil_img)
    if not q.ok:
        raise HTTPException(
            status_code=422,
            detail={"code": "image_quality", "reason": q.code, "message": q.message, "metrics": q.metrics},
        )

    context = _parse_capture_context(
        {
            "duration_days": duration_days,
            "severity": severity,
            "symptoms": [x.strip() for x in str(symptoms or "").split(",") if x.strip()],
            "triggers": [x.strip() for x in str(triggers or "").split(",") if x.strip()],
            "body_zone": body_zone,
        }
    )
    return _predict_image_response(pil_img=pil_img, scan_id=uuid.uuid4().hex, sid=sid, plan=plan, capture_context=context)


@app.post("/capture/compare")
async def capture_compare(
    current_file: UploadFile = File(...),
    baseline_file: UploadFile | None = File(default=None),
) -> Dict[str, Any]:
    current_raw = await current_file.read()
    if not current_raw:
        raise HTTPException(status_code=400, detail="Missing current image.")
    try:
        current_img = Image.open(BytesIO(current_raw))
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read current image.")

    baseline_img = None
    if baseline_file is not None:
        baseline_raw = await baseline_file.read()
        if baseline_raw:
            try:
                baseline_img = Image.open(BytesIO(baseline_raw))
            except Exception:
                baseline_img = None

    return {
        "capture_guidance": capture_guidance(current_img),
        "comparison": compare_captures(current_img, baseline_img),
    }


@app.post("/predict")
async def predict_endpoint(request: Request, file: UploadFile = File(...)) -> Dict[str, Any]:
    scan_id = uuid.uuid4().hex
    ip = request.client.host if request.client else ""
    if not _rate_limiter.allow(f"predict:{ip}", _predict_rate):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")

    sid = str(request.headers.get("X-Session-Id", "")).strip()
    plan = "free"
    if sid:
        try:
            plan = get_billing_status(sid).plan
        except Exception:
            plan = "free"
    if sid and plan != "pro" and _freemium_daily_max > 0:
        used = get_daily_scans(sid)
        if used >= _freemium_daily_max:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "freemium_limit",
                    "message": f"Daily free scan limit reached ({_freemium_daily_max}/day).",
                    "daily_max": _freemium_daily_max,
                    "daily_used": used,
                    "daily_remaining": 0,
                },
            )

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
        pass

    q = check_image_quality(pil_img)
    if not q.ok:
        raise HTTPException(
            status_code=422,
            detail={"code": "image_quality", "reason": q.code, "message": q.message, "metrics": q.metrics},
        )

    return _predict_image_response(pil_img=pil_img, scan_id=scan_id, sid=sid, plan=plan, capture_context={})


# Serve the cinematic landing site from the same origin so local preview is a single URL:
# - Open http://127.0.0.1:8000 to see the website
# - API remains available at /health and /predict
if _landing_dir.exists():
    app.mount("/", StaticFiles(directory=str(_landing_dir), html=True), name="site")
