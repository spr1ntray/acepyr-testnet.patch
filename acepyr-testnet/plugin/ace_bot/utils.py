from __future__ import annotations

import re
from typing import Iterable

from urllib.parse import quote, urlparse

from eth_account import Account

_PRIVATE_KEY_RE = re.compile(r"(?i)\b(?:0x)?[a-f0-9]{64}\b")
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]{10,})?")
_BEARER_RE = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-]{16,}")
_PROXY_CREDS_RE = re.compile(r"(//)([^/\s@:\"]+):([^/\s@\"]+)@")
_PROXY_CREDS_BARE_RE = re.compile(
    r"(?i)\b([a-z0-9._%+\-]{2,}):([^@\s/:]{2,})@([a-z0-9.\-]+):(\d{2,5})\b"
)


def normalize_private_key(value: str | None) -> str:
    text = (value or "").strip()
    if text.startswith("0x") or text.startswith("0X"):
        text = text[2:]
    if len(text) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in text):
        raise ValueError("bad_key")
    return "0x" + text.lower()


def normalize_proxy(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    if "://" in value:
        parsed = urlparse(value)
        if not parsed.hostname or not parsed.port:
            raise ValueError("invalid_proxy")
        scheme = parsed.scheme or "http"
        if parsed.username is None:
            return f"{scheme}://{parsed.hostname}:{parsed.port}"
        user = quote(parsed.username, safe="")
        password = quote(parsed.password or "", safe="")
        return f"{scheme}://{user}:{password}@{parsed.hostname}:{parsed.port}"
    parts = value.split(":")
    if len(parts) == 2:
        host, port = parts
        if not host or not port.isdigit():
            raise ValueError("invalid_proxy")
        return f"http://{host}:{port}"
    if len(parts) >= 4:
        host, port, user = parts[0], parts[1], parts[2]
        password = ":".join(parts[3:])
        if not host or not port.isdigit() or not user:
            raise ValueError("invalid_proxy")
        return f"http://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}"
    raise ValueError("invalid_proxy")


def address_from_key(private_key: str) -> str:
    account = Account.from_key(normalize_private_key(private_key))
    return account.address


def short_address(value: str | None) -> str:
    text = str(value or "")
    if text.startswith("0x") and len(text) > 12:
        return f"{text[:6]}...{text[-4:]}"
    return text or "-"


def scrub_secrets(text: str, extra: Iterable[str | None] = ()) -> str:
    result = str(text)
    for secret in extra:
        if not secret:
            continue
        s = str(secret)
        if len(s) >= 6:
            result = result.replace(s, "[REDACTED]")
        bare = s.replace("http://", "").replace("https://", "")
        if bare != s and len(bare) >= 6:
            result = result.replace(bare, "[REDACTED]")
        if "@" in bare:
            userinfo = bare.split("@", 1)[0]
            if ":" in userinfo and len(userinfo) >= 4:
                result = result.replace(userinfo, "***:***")
    result = _PRIVATE_KEY_RE.sub("[REDACTED_KEY]", result)
    result = _JWT_RE.sub("[REDACTED_JWT]", result)
    result = _BEARER_RE.sub(r"\1[REDACTED]", result)
    result = _PROXY_CREDS_RE.sub(r"\1***:***@", result)
    result = _PROXY_CREDS_BARE_RE.sub(r"***:***@\3:\4", result)
    return result
