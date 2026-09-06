"""Optional AdsPower fingerprint pull. Never starts Chrome."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from plugin.ace_bot.identity import BrowserIdentity, identity_from_adspower, pick_identity

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "local.adspower.net", "local.adspower.com"})
DEFAULT_API_BASE = "http://local.adspower.com:50325"


def _secret(holder: Any, name: str) -> str:
    try:
        value = holder.secret(name)
    except Exception:
        return ""
    return str(value or "").strip()


def identity_for(context: Any, account: Any) -> BrowserIdentity:
    base = pick_identity(account.id)
    profile_id = _secret(account, "adspower_profile")
    api_key = ""
    settings = getattr(context, "settings", None)
    if settings is not None:
        api_key = _secret(settings, "adspower_api")
    if not profile_id:
        return base
    row = fetch_profile(profile_id, api_key or None)
    if not row:
        return base
    return identity_from_adspower(row, base)


def fetch_profile(profile_id: str, api_key: str | None = None) -> dict[str, Any] | None:
    pid = (profile_id or "").strip()
    if len(pid) < 4:
        return None
    try:
        from curl_cffi import requests as cf
    except Exception:
        return None
    headers = {}
    if api_key and len(api_key) >= 4:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = cf.get(
            f"{DEFAULT_API_BASE}/api/v1/user/list",
            params={"user_id": pid, "page": 1, "page_size": 1},
            headers=headers,
            timeout=8,
            impersonate="chrome136",
        )
        data = resp.json() if resp.content else {}
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    listing = data.get("data") if isinstance(data.get("data"), dict) else data
    rows = listing.get("list") if isinstance(listing, dict) else None
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        host = urlparse(DEFAULT_API_BASE).hostname or ""
        if host.lower() not in LOCAL_HOSTS:
            return None
        return rows[0]
    return None
