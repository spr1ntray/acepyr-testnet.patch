from __future__ import annotations

import hashlib
import threading
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from .errors import SoftError
from .http import AceClient
from .parse import error_code, unwrap

CancelCheck = Callable[[], None]
Protect = Callable[[str], str]

_CONSENT_SURFACE = "testnet_entry_gate"
_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_ALPHABET = _LETTERS + "0123456789"


class NameBank:
    def __init__(self) -> None:
        self._taken: set[str] = set()
        self._lock = threading.Lock()

    def remember(self, name: str) -> None:
        key = (name or "").strip().lower()
        if not key:
            return
        with self._lock:
            self._taken.add(key)

    def claim(self, name: str) -> bool:
        key = (name or "").strip().lower()
        if not key:
            return False
        with self._lock:
            if key in self._taken:
                return False
            self._taken.add(key)
            return True


def mint_username(account_id: str, salt: str = "") -> str:
    digest = hashlib.sha256(f"{account_id}:{salt}".encode()).digest()
    first = _LETTERS[digest[0] % len(_LETTERS)]
    rest = "".join(_ALPHABET[digest[i] % len(_ALPHABET)] for i in range(1, 11))
    return first + rest


def username_candidates(account_id: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for index in range(16):
        name = mint_username(account_id, "" if index == 0 else str(index))
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    for _ in range(8):
        name = mint_username(account_id, uuid.uuid4().hex)
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def stable_dob(account_id: str) -> str:
    raw = hashlib.sha256((account_id or "acepyr").encode()).digest()
    year = 1984 + (raw[0] % 18)
    month = 1 + (raw[1] % 12)
    day = 1 + (raw[2] % 28)
    return f"{year:04d}-{month:02d}-{day:02d}"


def complete_profile(
    client: AceClient,
    *,
    account_id: str,
    check: CancelCheck,
    referral_code: str = "",
    existing: dict[str, Any] | None = None,
    protect: Protect | None = None,
    names: NameBank | None = None,
) -> str:
    bank = names or NameBank()
    _grant_consents(client, check)
    check()
    dob = stable_dob(account_id)
    current = str((existing or {}).get("username") or "").strip()
    needs = (existing or {}).get("needsUsername") is True or not current
    name = current
    if name:
        bank.remember(name)
    if needs:
        name = _claim_username(client, account_id, dob, check, bank)
        bank.remember(name)
    if referral_code:
        check()
        if not _apply_referral(client, username=name, dob=dob, code=referral_code, protect=protect):
            raise SoftError("referral", "Не удалось привязать аккаунт к родителю")
    return name


def _claim_username(
    client: AceClient,
    account_id: str,
    dob: str,
    check: CancelCheck,
    bank: NameBank,
) -> str:
    last = SoftError("username", "Не удалось задать ник в Acepyr")
    for name in username_candidates(account_id):
        check()
        if not bank.claim(name):
            continue
        if _username_taken(client, name):
            continue
        try:
            if _put_profile(client, name, dob):
                return name
        except SoftError as exc:
            last = exc
            if exc.code == "username_cooldown":
                raise
            continue
    raise last


def _apply_referral(
    client: AceClient,
    *,
    username: str,
    dob: str,
    code: str,
    protect: Protect | None,
) -> bool:
    token = (code or "").strip()
    if not token:
        return True
    if protect is not None:
        try:
            token = protect(token) or token
        except Exception:
            pass
    payload = client.post_json(
        "/api/auth/email-otp/complete",
        {
            "username": username,
            "dateOfBirth": dob,
            "referralCode": token,
            "marketingOptIn": False,
        },
    )
    if not isinstance(payload, dict):
        return True
    if payload.get("success") is False:
        blob = f"{error_code(payload)} {payload.get('error') or ''}".lower()
        if any(marker in blob for marker in ("already", "exists", "referred")):
            return True
        if error_code(payload).startswith("http_4"):
            return False
        return False
    return True


def _grant_consents(client: AceClient, check: CancelCheck) -> None:
    try:
        payload = client.get_json("/api/consent/required")
    except SoftError:
        return
    data = unwrap(payload) if isinstance(payload, dict) else payload
    if not isinstance(data, dict) or data.get("satisfied") is True:
        return
    rows = data.get("outstanding") or data.get("all") or []
    if not isinstance(rows, list):
        return
    for row in rows:
        check()
        if not isinstance(row, dict):
            continue
        kind = str(row.get("consentType") or row.get("consent_type") or "").strip()
        if not kind:
            continue
        digest = str(row.get("textHash") or row.get("text_hash") or "").strip()
        if not digest:
            digest = _consent_hash(client, kind)
        try:
            client.post_json(
                "/api/consent/grant",
                {
                    "consent_type": kind,
                    "surface": _CONSENT_SURFACE,
                    "text_hash": digest,
                },
            )
        except SoftError:
            continue


def _consent_hash(client: AceClient, kind: str) -> str:
    try:
        payload = client.get_json(f"/api/consent/text?type={quote(kind)}")
    except SoftError:
        return ""
    data = unwrap(payload) if isinstance(payload, dict) else payload
    if isinstance(data, dict):
        return str(data.get("textHash") or data.get("text_hash") or "").strip()
    return ""


def _username_taken(client: AceClient, name: str) -> bool:
    try:
        payload = client.get_json(f"/api/auth/check-username?username={quote(name)}")
    except SoftError:
        return False
    data = unwrap(payload) if isinstance(payload, dict) else payload
    if not isinstance(data, dict):
        return False
    if data.get("available") is False or data.get("taken") is True:
        return True
    return False


def _put_profile(client: AceClient, username: str, dob: str) -> bool:
    payload = client.put_json(
        "/api/settings/profile",
        {"username": username, "dateOfBirth": dob},
        extra_headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    if isinstance(payload, dict) and payload.get("success") is False:
        code = error_code(payload).lower()
        if "cooldown" in code:
            raise SoftError("username_cooldown", "Acepyr временно не даёт сменить ник")
        if "underage" in code or code == "http_403":
            raise SoftError("username_age", "Acepyr отклонил дату рождения")
        return False
    if isinstance(payload, dict) and error_code(payload).startswith("http_"):
        code = error_code(payload)
        if code == "http_409":
            return False
        if code == "http_403":
            raise SoftError("username_age", "Acepyr отклонил дату рождения")
        return False
    return True
