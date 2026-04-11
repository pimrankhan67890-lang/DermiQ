from __future__ import annotations

import json
import os
from typing import Any, Dict, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def get_supabase_config() -> Dict[str, Any]:
    url = str(os.getenv("SUPABASE_URL", "")).strip().rstrip("/")
    anon_key = str(os.getenv("SUPABASE_ANON_KEY", "")).strip()
    return {
        "enabled": bool(url and anon_key),
        "url": url,
        "anon_key": anon_key,
        "google_enabled": bool(url and anon_key),
    }


def exchange_supabase_token(access_token: str) -> Tuple[Dict[str, Any], str]:
    cfg = get_supabase_config()
    token = str(access_token or "").strip()
    if not cfg["enabled"]:
        return {}, "Supabase auth is not configured."
    if not token:
        return {}, "Missing access token."

    req = Request(
        f"{cfg['url']}/auth/v1/user",
        headers={
            "apikey": str(cfg["anon_key"]),
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        return {}, f"Supabase auth rejected the session ({exc.code})."
    except URLError:
        return {}, "Could not reach Supabase auth."
    except Exception:
        return {}, "Could not verify the Supabase session."

    if not isinstance(payload, dict):
        return {}, "Invalid Supabase response."

    user_id = str(payload.get("id", "")).strip()
    if not user_id:
        return {}, "Supabase user id missing."

    meta = payload.get("user_metadata", {})
    app_meta = payload.get("app_metadata", {})
    if not isinstance(meta, dict):
        meta = {}
    if not isinstance(app_meta, dict):
        app_meta = {}

    profile = {
        "user_id": user_id,
        "email": str(payload.get("email", "")).strip(),
        "full_name": str(meta.get("full_name") or meta.get("name") or "").strip(),
        "avatar_url": str(meta.get("avatar_url", "")).strip(),
        "provider": str(app_meta.get("provider") or "supabase").strip(),
    }
    return profile, ""
