from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.taxonomy import family_for_label


ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / "backend_data"
DB_PATH = DB_DIR / "tracker.db"


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  created_at INTEGER NOT NULL,
  last_seen_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  ts INTEGER NOT NULL,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_events_session_ts ON events(session_id, ts DESC);

CREATE TABLE IF NOT EXISTS daily_usage (
  session_id TEXT NOT NULL,
  day_utc INTEGER NOT NULL,
  scans INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY(session_id, day_utc),
  FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pro_accounts (
  pro_token TEXT PRIMARY KEY,
  created_at INTEGER NOT NULL,
  source TEXT NOT NULL,
  stripe_customer_id TEXT,
  stripe_subscription_id TEXT,
  stripe_email TEXT,
  active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS pro_links (
  session_id TEXT PRIMARY KEY,
  pro_token TEXT NOT NULL,
  linked_at INTEGER NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
  FOREIGN KEY(pro_token) REFERENCES pro_accounts(pro_token) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS profiles (
  user_id TEXT PRIMARY KEY,
  email TEXT,
  full_name TEXT,
  avatar_url TEXT,
  provider TEXT NOT NULL DEFAULT 'supabase',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS user_sessions (
  session_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  linked_at INTEGER NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
  FOREIGN KEY(user_id) REFERENCES profiles(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scans (
  scan_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  session_id TEXT,
  top_label TEXT NOT NULL,
  top_prob REAL NOT NULL,
  top3_json TEXT NOT NULL,
  backend TEXT NOT NULL,
  confidence_level TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  FOREIGN KEY(user_id) REFERENCES profiles(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_scans_user_created ON scans(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS tracked_products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  product_id TEXT NOT NULL,
  product_name TEXT,
  category TEXT,
  status TEXT NOT NULL,
  store_preference TEXT,
  notes TEXT,
  scan_id TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE(user_id, product_id),
  FOREIGN KEY(user_id) REFERENCES profiles(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tracked_products_user_updated ON tracked_products(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS routine_plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  scan_id TEXT,
  top_label TEXT,
  plan_json TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  FOREIGN KEY(user_id) REFERENCES profiles(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_routine_plans_user_updated ON routine_plans(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS follow_ups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  scan_id TEXT,
  severity REAL NOT NULL,
  notes TEXT,
  flags_json TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  FOREIGN KEY(user_id) REFERENCES profiles(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_followups_user_created ON follow_ups(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS user_feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  session_id TEXT,
  scan_id TEXT,
  rating INTEGER NOT NULL,
  accurate_label TEXT,
  notes TEXT,
  created_at INTEGER NOT NULL,
  FOREIGN KEY(user_id) REFERENCES profiles(user_id) ON DELETE CASCADE
);
"""


def _conn() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH.as_posix(), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    c = _conn()
    try:
        c.executescript(SCHEMA)
        c.commit()
    finally:
        c.close()


def _now() -> int:
    return int(time.time())


def create_session() -> str:
    init_db()
    sid = uuid.uuid4().hex
    now = _now()
    c = _conn()
    try:
        c.execute(
            "INSERT INTO sessions(session_id, created_at, last_seen_at) VALUES(?,?,?)",
            (sid, now, now),
        )
        c.commit()
    finally:
        c.close()
    return sid


def touch_session(session_id: str) -> None:
    if not session_id:
        return
    init_db()
    now = _now()
    c = _conn()
    try:
        cur = c.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session_id,))
        row = cur.fetchone()
        if row is None:
            c.execute(
                "INSERT INTO sessions(session_id, created_at, last_seen_at) VALUES(?,?,?)",
                (session_id, now, now),
            )
        else:
            c.execute("UPDATE sessions SET last_seen_at=? WHERE session_id=?", (now, session_id))
        c.commit()
    finally:
        c.close()


def add_event(session_id: str, kind: str, payload: Dict[str, Any], ts: Optional[int] = None) -> None:
    session_id = str(session_id or "").strip()
    kind = str(kind or "").strip()
    if not session_id or not kind:
        return
    init_db()
    touch_session(session_id)

    t = int(ts) if ts is not None else _now()
    blob = json.dumps(payload or {}, ensure_ascii=False)
    c = _conn()
    try:
        c.execute(
            "INSERT INTO events(session_id, ts, kind, payload) VALUES(?,?,?,?)",
            (session_id, t, kind, blob),
        )
        c.commit()
    finally:
        c.close()


def get_events(session_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    session_id = str(session_id or "").strip()
    if not session_id:
        return []
    init_db()
    touch_session(session_id)
    lim = max(1, min(int(limit), 500))
    c = _conn()
    try:
        cur = c.execute(
            "SELECT ts, kind, payload FROM events WHERE session_id=? ORDER BY ts DESC LIMIT ?",
            (session_id, lim),
        )
        rows = cur.fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            try:
                payload = json.loads(str(r["payload"]))
            except Exception:
                payload = {}
            out.append({"ts": int(r["ts"]), "kind": str(r["kind"]), "payload": payload})
        return out
    finally:
        c.close()


def delete_session(session_id: str) -> None:
    session_id = str(session_id or "").strip()
    if not session_id:
        return
    init_db()
    c = _conn()
    try:
        c.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
        c.commit()
    finally:
        c.close()


def _parse_payload(blob: Any) -> Dict[str, Any]:
    try:
        data = json.loads(str(blob))
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}


def get_analytics_summary(days: int = 30, session_id: str = "") -> Dict[str, Any]:
    init_db()
    session_id = str(session_id or "").strip()
    days_i = max(1, min(int(days), 365))
    cutoff = _now() - days_i * 86400

    c = _conn()
    try:
        params: Tuple[Any, ...]
        q = (
            "SELECT session_id, ts, kind, payload FROM events "
            "WHERE ts >= ? "
        )
        params = (cutoff,)
        if session_id:
            q += "AND session_id = ? "
            params = (cutoff, session_id)
        q += "ORDER BY ts DESC"
        rows = c.execute(q, params).fetchall()

        sessions = set()
        counts: Dict[str, int] = {}
        category_counts: Dict[str, int] = {}
        store_clicks: Dict[str, int] = {}
        product_clicks: Dict[str, Dict[str, Any]] = {}
        shortlist_counts: Dict[str, int] = {}
        routine_products: Dict[str, int] = {}
        analysis_labels: Dict[str, int] = {}

        for row in rows:
            sid = str(row["session_id"] or "").strip()
            if sid:
                sessions.add(sid)
            kind = str(row["kind"] or "").strip()
            counts[kind] = counts.get(kind, 0) + 1
            payload = _parse_payload(row["payload"])

            if kind == "product_view":
                cat = str(payload.get("category", "")).strip().lower()
                if cat:
                    category_counts[cat] = category_counts.get(cat, 0) + 1

            elif kind == "product_click":
                store = str(payload.get("store", "")).strip() or "Unknown"
                product_id = str(payload.get("product_id", "")).strip()
                store_clicks[store] = store_clicks.get(store, 0) + 1
                if product_id:
                    entry = product_clicks.setdefault(product_id, {"product_id": product_id, "clicks": 0, "stores": {}})
                    entry["clicks"] += 1
                    entry["stores"][store] = int(entry["stores"].get(store, 0)) + 1

            elif kind == "cart_update":
                for pid in payload.get("product_ids", []) if isinstance(payload.get("product_ids"), list) else []:
                    key = str(pid or "").strip()
                    if key:
                        shortlist_counts[key] = shortlist_counts.get(key, 0) + 1

            elif kind == "routine_generated":
                for pid in payload.get("selected_products", []) if isinstance(payload.get("selected_products"), list) else []:
                    key = str(pid or "").strip()
                    if key:
                        routine_products[key] = routine_products.get(key, 0) + 1

            elif kind == "analysis":
                label = str(payload.get("top_label", "")).strip()
                if label:
                    analysis_labels[label] = analysis_labels.get(label, 0) + 1

        def top_map(src: Dict[str, int], label_key: str) -> List[Dict[str, Any]]:
            return [
                {label_key: key, "count": value}
                for key, value in sorted(src.items(), key=lambda item: (-item[1], item[0]))[:8]
            ]

        product_rows = sorted(product_clicks.values(), key=lambda item: (-int(item["clicks"]), item["product_id"]))[:8]
        top_products = []
        for item in product_rows:
            top_products.append(
                {
                    "product_id": item["product_id"],
                    "clicks": int(item["clicks"]),
                    "stores": dict(sorted(item["stores"].items(), key=lambda pair: (-pair[1], pair[0]))),
                    "shortlists": int(shortlist_counts.get(item["product_id"], 0)),
                    "routine_plans": int(routine_products.get(item["product_id"], 0)),
                }
            )

        product_clicks_total = int(counts.get("product_click", 0))
        analyses_total = int(counts.get("analysis", 0))
        routines_total = int(counts.get("routine_generated", 0) + counts.get("routine_generated_ui", 0))
        ctr = round((product_clicks_total / analyses_total) * 100, 1) if analyses_total else 0.0
        routine_rate = round((routines_total / analyses_total) * 100, 1) if analyses_total else 0.0

        return {
            "days": days_i,
            "scope": "session" if session_id else "global",
            "session_id": session_id,
            "summary": {
                "sessions": len(sessions) if not session_id else (1 if rows else 0),
                "analyses": analyses_total,
                "product_views": int(counts.get("product_view", 0)),
                "product_clicks": product_clicks_total,
                "cart_updates": int(counts.get("cart_update", 0)),
                "routine_plans": routines_total,
                "checkout_starts": int(counts.get("billing_checkout_started", 0)),
                "pro_unlocks": int(counts.get("pro_linked", 0)),
                "click_through_rate": ctr,
                "routine_rate": routine_rate,
            },
            "top_categories": top_map(category_counts, "category"),
            "top_stores": top_map(store_clicks, "store"),
            "top_conditions": top_map(analysis_labels, "label"),
            "top_products": top_products,
        }
    finally:
        c.close()


def _day_utc(ts: Optional[int] = None) -> int:
    t = int(ts) if ts is not None else _now()
    return int(t // 86400)


def get_daily_scans(session_id: str, day_utc: Optional[int] = None) -> int:
    session_id = str(session_id or "").strip()
    if not session_id:
        return 0
    init_db()
    touch_session(session_id)
    day = int(day_utc) if day_utc is not None else _day_utc()
    c = _conn()
    try:
        cur = c.execute(
            "SELECT scans FROM daily_usage WHERE session_id=? AND day_utc=?",
            (session_id, day),
        )
        row = cur.fetchone()
        if row is None:
            return 0
        try:
            return int(row["scans"])
        except Exception:
            return 0
    finally:
        c.close()


def incr_daily_scans(session_id: str, day_utc: Optional[int] = None) -> int:
    session_id = str(session_id or "").strip()
    if not session_id:
        return 0
    init_db()
    touch_session(session_id)
    day = int(day_utc) if day_utc is not None else _day_utc()
    now = _now()
    c = _conn()
    try:
        c.execute(
            "INSERT INTO daily_usage(session_id, day_utc, scans, updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(session_id, day_utc) DO UPDATE SET scans=scans+1, updated_at=excluded.updated_at",
            (session_id, day, 1, now),
        )
        c.commit()
        cur = c.execute("SELECT scans FROM daily_usage WHERE session_id=? AND day_utc=?", (session_id, day))
        row = cur.fetchone()
        try:
            return int(row["scans"]) if row is not None else 0
        except Exception:
            return 0
    finally:
        c.close()


@dataclass(frozen=True)
class Escalation:
    should_consult: bool
    reason: str
    level: str  # "none" | "caution" | "urgent"


def _extract_symptoms(events: List[Dict[str, Any]]) -> List[Tuple[int, float]]:
    pts: List[Tuple[int, float]] = []
    for e in events:
        if e.get("kind") != "symptom":
            continue
        ts = int(e.get("ts") or 0)
        p = e.get("payload") or {}
        try:
            sev = float(p.get("severity", 0))
        except Exception:
            sev = 0.0
        pts.append((ts, sev))
    pts.sort(key=lambda x: x[0])
    return pts


def assess_escalation(events: List[Dict[str, Any]]) -> Escalation:
    """
    Simple, safety-first escalation rules.
    """
    # Red flags => urgent.
    for e in events[:50]:
        if e.get("kind") != "red_flag":
            continue
        p = e.get("payload") or {}
        flags = p.get("flags")
        if isinstance(flags, list) and any(bool(x) for x in flags):
            return Escalation(True, "Red-flag symptoms reported.", "urgent")

    symptoms = _extract_symptoms(events)
    if symptoms:
        # High severity => consult.
        if symptoms and max(s for _t, s in symptoms[-5:]) >= 8:
            return Escalation(True, "High symptom severity reported.", "urgent")

        # No improvement over time (very basic).
        # Compare average of first 3 vs last 3 symptom logs if at least 6 points and 10+ days span.
        if len(symptoms) >= 6:
            t0, _ = symptoms[0]
            t1, _ = symptoms[-1]
            days = (t1 - t0) / 86400.0 if t1 > t0 else 0.0
            if days >= 10:
                first_avg = sum(s for _t, s in symptoms[:3]) / 3.0
                last_avg = sum(s for _t, s in symptoms[-3:]) / 3.0
                if last_avg >= first_avg - 0.5:
                    return Escalation(True, "Symptoms not improving over ~10 days.", "caution")

    # Also if multiple analyses in a row show very low confidence.
    low_conf = 0
    for e in events:
        if e.get("kind") != "analysis":
            continue
        p = e.get("payload") or {}
        try:
            top_prob = float(p.get("top_prob", 0.0))
        except Exception:
            top_prob = 0.0
        if top_prob < 0.45:
            low_conf += 1
        if low_conf >= 3:
            return Escalation(True, "Low-confidence results repeatedly.", "caution")

    return Escalation(False, "", "none")


def _json_blob(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _avg(values: List[float]) -> float:
    nums = [float(v) for v in values if v is not None]
    return (sum(nums) / len(nums)) if nums else 0.0


def _confidence_mode(top_label: str, top_prob: float, escalation_level: str = "none") -> str:
    label = str(top_label or "").strip().lower()
    prob = float(top_prob or 0.0)
    esc = str(escalation_level or "none").strip().lower()
    if esc == "urgent":
        return "escalate"
    if label == "uncertain" or prob < 0.45:
        return "uncertain"
    if esc == "caution" or prob < 0.7:
        return "watch"
    return "confident"


def _trend_from_followups(follow_ups: List[Dict[str, Any]]) -> str:
    if len(follow_ups) < 2:
        return "unknown"
    recent = [float(item.get("severity", 0.0)) for item in follow_ups[:3]]
    older = [float(item.get("severity", 0.0)) for item in follow_ups[3:6]]
    if not older:
        delta = recent[0] - recent[-1] if len(recent) >= 2 else 0.0
        if delta >= 1.0:
            return "improving"
        if delta <= -1.0:
            return "worsening"
        return "steady"
    recent_avg = _avg(recent)
    older_avg = _avg(older)
    if recent_avg <= older_avg - 0.75:
        return "improving"
    if recent_avg >= older_avg + 0.75:
        return "worsening"
    return "steady"


def derive_case_state(
    *,
    scans: List[Dict[str, Any]],
    follow_ups: List[Dict[str, Any]],
    products: List[Dict[str, Any]],
    escalation: Dict[str, Any],
) -> Dict[str, Any]:
    latest_scan = scans[0] if scans else {}
    top_label = str(latest_scan.get("top_label") or "").strip()
    top_prob = float(latest_scan.get("top_prob") or 0.0)
    escalation_level = str(escalation.get("level") or "none").strip().lower()
    confidence_mode = _confidence_mode(top_label, top_prob, escalation_level)

    follow_flags: List[str] = []
    for item in follow_ups[:4]:
        flags = item.get("flags") if isinstance(item.get("flags"), dict) else {}
        for key, label in [
            ("fever", "Fever"),
            ("spreading_fast", "Spreading fast"),
            ("bleeding", "Bleeding"),
            ("eye_involvement", "Eye involvement"),
            ("severe_pain", "Severe pain"),
        ]:
            if flags.get(key):
                follow_flags.append(label)
    irritation_flags = [str(item.get("name") or item.get("product_id") or "Product") for item in products if str(item.get("status") or "") == "irritated"][:4]
    neutral_count = sum(1 for item in products if str(item.get("status") or "") == "neutral")
    inconsistent_count = sum(1 for item in products if str(item.get("status") or "") == "inconsistent")
    active_count = sum(1 for item in products if str(item.get("status") or "") in {"active", "helped"})
    helped_count = sum(1 for item in products if str(item.get("status") or "") == "helped")

    latest_severity = float(follow_ups[0].get("severity", 0.0)) if follow_ups else 0.0
    trend = _trend_from_followups(follow_ups)

    return {
        "focus_condition": top_label,
        "focus_family": family_for_label(top_label),
        "confidence_mode": confidence_mode,
        "symptom_severity": latest_severity,
        "response_trend": trend,
        "escalation_status": escalation_level or "none",
        "consult_recommended": escalation_level in {"caution", "urgent"},
        "irritation_flags": irritation_flags,
        "red_flag_signals": _uniq_preserve(follow_flags),
        "products_in_use": active_count,
        "helped_products": helped_count,
        "neutral_products": neutral_count,
        "inconsistent_products": inconsistent_count,
        "last_check_in_at": int(follow_ups[0].get("created_at") or 0) if follow_ups else 0,
        "last_scan_at": int(latest_scan.get("created_at") or 0) if latest_scan else 0,
    }


def _uniq_preserve(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        key = str(item or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def upsert_profile(
    user_id: str,
    *,
    email: str = "",
    full_name: str = "",
    avatar_url: str = "",
    provider: str = "supabase",
) -> None:
    user_id = str(user_id or "").strip()
    if not user_id:
        return
    init_db()
    now = _now()
    c = _conn()
    try:
        c.execute(
            """
            INSERT INTO profiles(user_id, email, full_name, avatar_url, provider, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
              email=excluded.email,
              full_name=excluded.full_name,
              avatar_url=excluded.avatar_url,
              provider=excluded.provider,
              updated_at=excluded.updated_at
            """,
            (user_id, email.strip(), full_name.strip(), avatar_url.strip(), provider.strip() or "supabase", now, now),
        )
        c.commit()
    finally:
        c.close()


def link_session_to_user(session_id: str, user_id: str) -> None:
    session_id = str(session_id or "").strip()
    user_id = str(user_id or "").strip()
    if not session_id or not user_id:
        return
    init_db()
    touch_session(session_id)
    c = _conn()
    try:
        c.execute(
            """
            INSERT INTO user_sessions(session_id, user_id, linked_at)
            VALUES(?,?,?)
            ON CONFLICT(session_id) DO UPDATE SET
              user_id=excluded.user_id,
              linked_at=excluded.linked_at
            """,
            (session_id, user_id, _now()),
        )
        c.commit()
    finally:
        c.close()


def get_user_id_for_session(session_id: str) -> str:
    session_id = str(session_id or "").strip()
    if not session_id:
        return ""
    init_db()
    c = _conn()
    try:
        row = c.execute("SELECT user_id FROM user_sessions WHERE session_id=?", (session_id,)).fetchone()
        return str(row["user_id"]).strip() if row and row["user_id"] else ""
    finally:
        c.close()


def get_profile(user_id: str) -> Dict[str, Any]:
    user_id = str(user_id or "").strip()
    if not user_id:
        return {}
    init_db()
    c = _conn()
    try:
        row = c.execute(
            "SELECT user_id, email, full_name, avatar_url, provider, created_at, updated_at FROM profiles WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if not row:
            return {}
        return {
            "user_id": str(row["user_id"]),
            "email": str(row["email"] or ""),
            "full_name": str(row["full_name"] or ""),
            "avatar_url": str(row["avatar_url"] or ""),
            "provider": str(row["provider"] or "supabase"),
            "created_at": int(row["created_at"] or 0),
            "updated_at": int(row["updated_at"] or 0),
        }
    finally:
        c.close()


def save_scan_record(
    *,
    user_id: str,
    scan_id: str,
    session_id: str,
    top_label: str,
    top_prob: float,
    top3: List[Dict[str, Any]],
    backend: str,
) -> None:
    user_id = str(user_id or "").strip()
    scan_id = str(scan_id or "").strip()
    if not user_id or not scan_id:
        return
    init_db()
    c = _conn()
    try:
        confidence_level = _confidence_mode(str(top_label or "").strip(), float(top_prob or 0.0))
        c.execute(
            """
            INSERT OR REPLACE INTO scans(
              scan_id, user_id, session_id, top_label, top_prob, top3_json, backend, confidence_level, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                scan_id,
                user_id,
                str(session_id or "").strip(),
                str(top_label or "").strip(),
                float(top_prob),
                _json_blob(top3),
                str(backend or "").strip(),
                confidence_level,
                _now(),
            ),
        )
        c.commit()
    finally:
        c.close()


def list_user_scans(user_id: str, limit: int = 12) -> List[Dict[str, Any]]:
    user_id = str(user_id or "").strip()
    if not user_id:
        return []
    init_db()
    lim = max(1, min(int(limit), 100))
    c = _conn()
    try:
        rows = c.execute(
            """
            SELECT scan_id, top_label, top_prob, top3_json, backend, confidence_level, created_at
            FROM scans
            WHERE user_id=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, lim),
        ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "scan_id": str(row["scan_id"] or ""),
                    "top_label": str(row["top_label"] or ""),
                    "top_prob": float(row["top_prob"] or 0.0),
                    "top3": _parse_payload(row["top3_json"]) if str(row["top3_json"] or "").startswith("{") else json.loads(str(row["top3_json"] or "[]") or "[]"),
                    "backend": str(row["backend"] or ""),
                    "confidence_level": str(row["confidence_level"] or "low"),
                    "created_at": int(row["created_at"] or 0),
                }
            )
        return out
    finally:
        c.close()


def save_tracked_products(
    user_id: str,
    products: List[Dict[str, Any]],
    *,
    scan_id: str = "",
    default_status: str = "planned",
    preferred_store: str = "",
    notes: str = "",
) -> List[Dict[str, Any]]:
    user_id = str(user_id or "").strip()
    if not user_id:
        return []
    init_db()
    now = _now()
    c = _conn()
    try:
        for item in products or []:
            if not isinstance(item, dict):
                continue
            product_id = str(item.get("id", "")).strip()
            if not product_id:
                continue
            c.execute(
                """
                INSERT INTO tracked_products(
                  user_id, product_id, product_name, category, status, store_preference, notes, scan_id, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(user_id, product_id) DO UPDATE SET
                  product_name=excluded.product_name,
                  category=excluded.category,
                  store_preference=CASE
                    WHEN excluded.store_preference <> '' THEN excluded.store_preference
                    ELSE tracked_products.store_preference
                  END,
                  notes=CASE
                    WHEN excluded.notes <> '' THEN excluded.notes
                    ELSE tracked_products.notes
                  END,
                  scan_id=CASE
                    WHEN excluded.scan_id <> '' THEN excluded.scan_id
                    ELSE tracked_products.scan_id
                  END,
                  updated_at=excluded.updated_at
                """,
                (
                    user_id,
                    product_id,
                    str(item.get("name", "")).strip(),
                    str(item.get("category", "")).strip(),
                    str(default_status or "planned").strip(),
                    str(preferred_store or "").strip(),
                    str(notes or "").strip(),
                    str(scan_id or "").strip(),
                    now,
                    now,
                ),
            )
        c.commit()
    finally:
        c.close()
    return list_tracked_products(user_id)


def update_tracked_product_status(user_id: str, product_id: str, status: str, notes: str = "") -> Dict[str, Any]:
    user_id = str(user_id or "").strip()
    product_id = str(product_id or "").strip()
    if not user_id or not product_id:
        return {}
    status = str(status or "planned").strip().lower()
    if status not in {"planned", "active", "helped", "neutral", "irritated", "inconsistent", "stopped"}:
        status = "planned"
    init_db()
    c = _conn()
    try:
        c.execute(
            """
            UPDATE tracked_products
            SET status=?, notes=CASE WHEN ? <> '' THEN ? ELSE notes END, updated_at=?
            WHERE user_id=? AND product_id=?
            """,
            (status, str(notes or "").strip(), str(notes or "").strip(), _now(), user_id, product_id),
        )
        c.commit()
    finally:
        c.close()
    for item in list_tracked_products(user_id):
        if str(item.get("product_id")) == product_id:
            return item
    return {}


def list_tracked_products(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    user_id = str(user_id or "").strip()
    if not user_id:
        return []
    init_db()
    lim = max(1, min(int(limit), 200))
    c = _conn()
    try:
        rows = c.execute(
            """
            SELECT product_id, product_name, category, status, store_preference, notes, scan_id, created_at, updated_at
            FROM tracked_products
            WHERE user_id=?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (user_id, lim),
        ).fetchall()
        return [
            {
                "product_id": str(row["product_id"] or ""),
                "name": str(row["product_name"] or ""),
                "category": str(row["category"] or ""),
                "status": str(row["status"] or "planned"),
                "store_preference": str(row["store_preference"] or ""),
                "notes": str(row["notes"] or ""),
                "scan_id": str(row["scan_id"] or ""),
                "created_at": int(row["created_at"] or 0),
                "updated_at": int(row["updated_at"] or 0),
            }
            for row in rows
        ]
    finally:
        c.close()


def save_routine_plan_record(user_id: str, scan_id: str, top_label: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    user_id = str(user_id or "").strip()
    if not user_id:
        return {}
    init_db()
    now = _now()
    c = _conn()
    try:
        c.execute(
            """
            INSERT INTO routine_plans(user_id, scan_id, top_label, plan_json, created_at, updated_at)
            VALUES(?,?,?,?,?,?)
            """,
            (user_id, str(scan_id or "").strip(), str(top_label or "").strip(), _json_blob(plan), now, now),
        )
        c.commit()
    finally:
        c.close()
    return get_latest_routine_plan(user_id)


def get_latest_routine_plan(user_id: str) -> Dict[str, Any]:
    user_id = str(user_id or "").strip()
    if not user_id:
        return {}
    init_db()
    c = _conn()
    try:
        row = c.execute(
            """
            SELECT id, scan_id, top_label, plan_json, created_at, updated_at
            FROM routine_plans
            WHERE user_id=?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        if not row:
            return {}
        return {
            "id": int(row["id"] or 0),
            "scan_id": str(row["scan_id"] or ""),
            "top_label": str(row["top_label"] or ""),
            "plan": _parse_payload(row["plan_json"]) if str(row["plan_json"] or "").startswith("{") else json.loads(str(row["plan_json"] or "{}")),
            "created_at": int(row["created_at"] or 0),
            "updated_at": int(row["updated_at"] or 0),
        }
    finally:
        c.close()


def save_follow_up_record(
    user_id: str,
    *,
    severity: float,
    notes: str = "",
    flags: Dict[str, Any] | None = None,
    scan_id: str = "",
) -> Dict[str, Any]:
    user_id = str(user_id or "").strip()
    if not user_id:
        return {}
    init_db()
    payload = flags if isinstance(flags, dict) else {}
    now = _now()
    c = _conn()
    try:
        c.execute(
            """
            INSERT INTO follow_ups(user_id, scan_id, severity, notes, flags_json, created_at)
            VALUES(?,?,?,?,?,?)
            """,
            (user_id, str(scan_id or "").strip(), float(severity), str(notes or "").strip(), _json_blob(payload), now),
        )
        c.commit()
    finally:
        c.close()
    records = list_follow_ups(user_id, limit=1)
    return records[0] if records else {}


def list_follow_ups(user_id: str, limit: int = 12) -> List[Dict[str, Any]]:
    user_id = str(user_id or "").strip()
    if not user_id:
        return []
    init_db()
    lim = max(1, min(int(limit), 100))
    c = _conn()
    try:
        rows = c.execute(
            """
            SELECT id, scan_id, severity, notes, flags_json, created_at
            FROM follow_ups
            WHERE user_id=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, lim),
        ).fetchall()
        return [
            {
                "id": int(row["id"] or 0),
                "scan_id": str(row["scan_id"] or ""),
                "severity": float(row["severity"] or 0.0),
                "notes": str(row["notes"] or ""),
                "flags": _parse_payload(row["flags_json"]),
                "created_at": int(row["created_at"] or 0),
            }
            for row in rows
        ]
    finally:
        c.close()


def save_feedback_record(
    *,
    user_id: str = "",
    session_id: str = "",
    scan_id: str = "",
    rating: int = 0,
    accurate_label: str = "",
    notes: str = "",
) -> None:
    init_db()
    c = _conn()
    try:
        c.execute(
            """
            INSERT INTO user_feedback(user_id, session_id, scan_id, rating, accurate_label, notes, created_at)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                str(user_id or "").strip() or None,
                str(session_id or "").strip() or None,
                str(scan_id or "").strip() or None,
                int(rating),
                str(accurate_label or "").strip(),
                str(notes or "").strip(),
                _now(),
            ),
        )
        c.commit()
    finally:
        c.close()


def assess_user_escalation(user_id: str) -> Dict[str, Any]:
    user_id = str(user_id or "").strip()
    if not user_id:
        return {"level": "none", "reason": "", "next_step": ""}

    follow_ups = list_follow_ups(user_id, limit=8)
    scans = list_user_scans(user_id, limit=6)
    products = list_tracked_products(user_id, limit=20)

    for item in follow_ups:
        flags = item.get("flags") if isinstance(item.get("flags"), dict) else {}
        if any(bool(flags.get(k)) for k in ["fever", "spreading_fast", "bleeding", "eye_involvement", "severe_pain"]):
            return {
                "level": "urgent",
                "reason": "Red-flag symptoms were reported in a follow-up.",
                "next_step": "Consult a licensed clinician promptly instead of trying more products.",
            }

    if follow_ups and float(follow_ups[0].get("severity", 0.0)) >= 8:
        return {
            "level": "urgent",
            "reason": "Symptom severity remains high.",
            "next_step": "Please seek a dermatologist or clinician promptly.",
        }

    if len(follow_ups) >= 3:
        recent = [float(item.get("severity", 0.0)) for item in follow_ups[:3]]
        older = [float(item.get("severity", 0.0)) for item in follow_ups[3:6]] if len(follow_ups) >= 6 else []
        if older and (sum(recent) / len(recent)) >= (sum(older) / len(older)):
            return {
                "level": "caution",
                "reason": "Your follow-ups do not show clear improvement yet.",
                "next_step": "Keep the routine simple and consider a clinician if this continues another week.",
            }
        if len(recent) >= 2 and recent[0] >= recent[-1] + 2:
            return {
                "level": "caution",
                "reason": "Symptoms look worse than your earlier follow-ups.",
                "next_step": "Stop adding new products and consider a clinician if this trend continues.",
            }

    low_conf = 0
    for scan in scans:
        if str(scan.get("top_label") or "") == "uncertain" or float(scan.get("top_prob") or 0.0) < 0.45:
            low_conf += 1
    if low_conf >= 2:
        return {
            "level": "caution",
            "reason": "Recent scans were low-confidence or uncertain.",
            "next_step": "Take a clearer close-up photo or consider consulting a clinician for confirmation.",
        }

    irritated_count = sum(1 for item in products if str(item.get("status") or "") == "irritated")
    if irritated_count >= 1:
        return {
            "level": "caution",
            "reason": "At least one tracked product was marked as irritating.",
            "next_step": "Stop the irritating product and keep the routine gentle.",
        }

    inconsistent_count = sum(1 for item in products if str(item.get("status") or "") == "inconsistent")
    if inconsistent_count >= 2:
        return {
            "level": "caution",
            "reason": "Your product use looks inconsistent, so DermIQ cannot tell what is helping yet.",
            "next_step": "Keep the routine simple and use one new product at a time for 1 week.",
        }

    return {"level": "none", "reason": "", "next_step": "Keep tracking weekly so DermIQ can spot changes early."}


def get_journey_summary(user_id: str) -> Dict[str, Any]:
    user_id = str(user_id or "").strip()
    if not user_id:
        return {}
    profile = get_profile(user_id)
    scans = list_user_scans(user_id, limit=8)
    products = list_tracked_products(user_id, limit=20)
    routine = get_latest_routine_plan(user_id)
    follow_ups = list_follow_ups(user_id, limit=8)
    escalation = assess_user_escalation(user_id)
    case_state = derive_case_state(scans=scans, follow_ups=follow_ups, products=products, escalation=escalation)

    current_condition = scans[0]["top_label"] if scans else ""
    trend = str(case_state.get("response_trend") or "unknown")
    stats = {
        "total_scans": len(scans),
        "tracked_products": len(products),
        "active_products": sum(1 for item in products if str(item.get("status") or "") in {"active", "helped"}),
        "follow_ups": len(follow_ups),
        "helped_products": sum(1 for item in products if str(item.get("status") or "") == "helped"),
        "irritated_products": sum(1 for item in products if str(item.get("status") or "") == "irritated"),
    }
    return {
        "profile": profile,
        "stats": stats,
        "current_condition": current_condition,
        "case_state": case_state,
        "progress_signal": {
            "trend": trend,
            "latest_severity": float(case_state.get("symptom_severity") or 0.0),
            "confidence_mode": str(case_state.get("confidence_mode") or "uncertain"),
        },
        "recent_scans": scans,
        "products": products,
        "routine": routine,
        "follow_ups": follow_ups,
        "escalation": escalation,
    }


def delete_user_data(user_id: str) -> None:
    user_id = str(user_id or "").strip()
    if not user_id:
        return
    init_db()
    c = _conn()
    try:
        c.execute("DELETE FROM profiles WHERE user_id=?", (user_id,))
        c.commit()
    finally:
        c.close()
