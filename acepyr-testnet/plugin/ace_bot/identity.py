from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BrowserIdentity:
    index: int
    device_id: str
    user_agent: str
    sec_ch_ua: str
    sec_ch_ua_mobile: str
    sec_ch_ua_platform: str
    platform: str
    accept_language: str
    languages: tuple[str, ...]
    timezone: str
    screen: str
    hardware_concurrency: int
    device_memory: int
    chrome_major: int
    impersonate: str
    source: str = "bank"


def _bank_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "identities.json"


def load_bank() -> list[dict[str, Any]]:
    payload = json.loads(_bank_path().read_text(encoding="utf-8"))
    if not isinstance(payload, list) or len(payload) < 200:
        raise ValueError("identity_bank_empty")
    return payload


def _from_row(row: dict[str, Any], *, source: str) -> BrowserIdentity:
    langs = row.get("languages") or []
    if isinstance(langs, str):
        languages = tuple(part.strip() for part in langs.split(",") if part.strip())
    else:
        languages = tuple(str(item) for item in langs)
    ua = str(row.get("user_agent") or "")
    platform = str(row.get("platform") or "Windows")
    if "macintosh" in ua.lower() or "mac os" in ua.lower():
        platform = "macOS"
    elif "windows" in ua.lower():
        platform = "Windows"
    major = int(row.get("chrome_major") or chrome_major(ua) or 136)
    return BrowserIdentity(
        index=int(row.get("index") or 0),
        device_id=str(row.get("device_id") or ""),
        user_agent=frozen_user_agent(platform, major),
        sec_ch_ua=client_hints(major),
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform='"macOS"' if platform == "macOS" else '"Windows"',
        platform=platform,
        accept_language=str(row.get("accept_language") or "en-US,en;q=0.9"),
        languages=languages or ("en-US", "en"),
        timezone=str(row.get("timezone") or "America/New_York"),
        screen=str(row.get("screen") or "1920x1080"),
        hardware_concurrency=int(row.get("hardware_concurrency") or 8),
        device_memory=int(row.get("device_memory") or 8),
        chrome_major=major,
        impersonate=impersonate_for(major),
        source=source,
    )


def pick_identity(account_id: str, bank: list[dict[str, Any]] | None = None) -> BrowserIdentity:
    rows = bank if bank is not None else load_bank()
    digest = hashlib.sha256(f"acepyr-identity:{account_id}".encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(rows)
    return _from_row(rows[index], source="bank")


_GREASE = {
    120: '"Not_A Brand";v="8"',
    124: '"Not)A;Brand";v="24"',
    131: '"Not=A?Brand";v="24"',
    136: '"Not.A/Brand";v="99"',
}


def chrome_major(user_agent: str) -> int:
    found = re.search(r"Chrome/(\d+)", user_agent or "")
    return int(found.group(1)) if found else 0


def impersonate_for(major: int) -> str:
    if major >= 136:
        return "chrome136"
    if major >= 131:
        return "chrome131"
    if major >= 124:
        return "chrome124"
    return "chrome120"


def frozen_user_agent(platform: str, major: int) -> str:
    if platform == "macOS":
        return (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
        )
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
    )


def client_hints(major: int) -> str:
    grease = _GREASE.get(major, '"Not=A?Brand";v="99"')
    return f'{grease}, "Google Chrome";v="{major}", "Chromium";v="{major}"'


def identity_from_adspower(profile: dict[str, Any], fallback: BrowserIdentity) -> BrowserIdentity:
    fp = profile.get("fingerprint_config") if isinstance(profile.get("fingerprint_config"), dict) else profile
    if not isinstance(fp, dict):
        fp = profile if isinstance(profile, dict) else {}
    raw_ua = str(fp.get("ua") or profile.get("ua") or fallback.user_agent)
    major = chrome_major(raw_ua) or fallback.chrome_major
    language = fp.get("language") or list(fallback.languages)
    if isinstance(language, str):
        langs = tuple(part.strip() for part in language.replace(";", ",").split(",") if part.strip())
    else:
        langs = tuple(str(item) for item in language)
    accept = ",".join(
        f"{lang};q={max(0.7, 1 - index * 0.1):.1f}" if index else lang for index, lang in enumerate(langs[:4])
    )
    screen = str(fp.get("screen_resolution") or fp.get("screen") or fallback.screen).replace("_", "x")
    platform = "macOS" if "macintosh" in raw_ua.lower() or "mac os" in raw_ua.lower() else "Windows"
    ch_platform = '"macOS"' if platform == "macOS" else '"Windows"'
    return replace(
        fallback,
        user_agent=frozen_user_agent(platform, major),
        sec_ch_ua=client_hints(major),
        sec_ch_ua_mobile="?0",
        sec_ch_ua_platform=ch_platform,
        platform=platform,
        accept_language=accept or fallback.accept_language,
        languages=langs or fallback.languages,
        timezone=str(fp.get("timezone") or fallback.timezone),
        screen=screen,
        hardware_concurrency=int(fp.get("hardware_concurrency") or fallback.hardware_concurrency),
        device_memory=int(fp.get("device_memory") or fallback.device_memory),
        chrome_major=major,
        impersonate=impersonate_for(major),
        source="adspower",
    )
