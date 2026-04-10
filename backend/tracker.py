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

