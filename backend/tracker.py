from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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
