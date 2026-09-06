from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from .capsolver import solve_turnstile
from .config import (
    ORIGIN,
    SIWE_CHAIN_ID,
    SUPABASE_ANON,
    SUPABASE_URL,
    TURNSTILE_PAGE,
    TURNSTILE_SITEKEY,
    WALLET_AUTH_STATEMENT,
)
from .errors import BlockedError, SoftError
from .http import AceClient
from .onboard import NameBank, complete_profile
from .parse import error_code, error_message, parse_me
from .utils import address_from_key
from .wallet import sign_message, siwe_message

CancelCheck = Callable[[], None]


def _protect(protect: Callable[[str], str] | None, value: str) -> str:
    if protect is None:
        return value
    try:
        return protect(value) or value
    except Exception:
        return value


def _turnstile(
    capsolver_key: str,
    proxy: str | None,
    protect: Callable[[str], str] | None,
    *,
    action: str,
    check: CancelCheck | None,
) -> str:
    token = solve_turnstile(
        capsolver_key,
        site_key=TURNSTILE_SITEKEY,
        page_url=TURNSTILE_PAGE,
        proxy=proxy,
        action=action,
        check=check,
    )
    return _protect(protect, token)


def ensure_session(
    client: AceClient,
    *,
    account_id: str,
    private_key: str,
    capsolver_key: str,
    proxy: str | None,
    check: CancelCheck,
    protect: Callable[[str], str] | None = None,
    referral_code: str = "",
    names: NameBank | None = None,
) -> dict[str, Any]:
    user = None
    try:
        user = parse_me(client.get_json("/api/auth/me"))
    except BlockedError:
        user = None
    if user is None:
        check()
        try:
            client.get_text("/live")
        except SoftError:
            pass
        check()
        login_with_wallet(
            client,
            private_key=private_key,
            capsolver_key=capsolver_key,
            proxy=proxy,
            protect=protect,
            check=check,
        )
        check()
    user = _finish_session(
        client,
        account_id=account_id,
        referral_code=referral_code,
        check=check,
        protect=protect,
        names=names,
    )
    if user:
        return user
    raise BlockedError("not_logged_in", "Не удалось войти в Acepyr")


def login_with_wallet(
    client: AceClient,
    *,
    private_key: str,
    capsolver_key: str,
    proxy: str | None,
    protect: Callable[[str], str] | None = None,
    check: CancelCheck | None = None,
) -> None:
    waiter = check or (lambda: None)
    address = address_from_key(private_key)
    captcha = _turnstile(
        capsolver_key, proxy, protect, action="login", check=waiter
    )
    waiter()
    issued = (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    message = siwe_message(
        address,
        issued_at=issued,
        uri=TURNSTILE_PAGE,
        chain_id=SIWE_CHAIN_ID,
        statement=WALLET_AUTH_STATEMENT,
    )
    signature = sign_message(private_key, message)
    waiter()
    status, payload = client.request_url(
        "POST",
        f"{SUPABASE_URL}/auth/v1/token?grant_type=web3",
        json_body={
            "chain": "ethereum",
            "message": message,
            "signature": signature,
            "gotrue_meta_security": {"captcha_token": captcha},
        },
        headers=_supabase_headers(),
    )
    if status == 429:
        raise SoftError("rate_limit", "Acepyr просит подождать")
    if _is_captcha_error(payload, status):
        raise SoftError("captcha", "Turnstile не принят Acepyr")
    access = _access_token(payload)
    if status >= 400 or not access:
        raise SoftError("auth_wallet", "Acepyr не принял подпись кошелька")
    client.set_bearer(_protect(protect, access))
    _record_session(client)


def _record_session(client: AceClient) -> None:
    try:
        client.post_json("/api/auth/session/record", {})
    except SoftError:
        pass
    try:
        client.post_json("/api/user/identity/sync", {})
    except SoftError:
        pass


def _finish_session(
    client: AceClient,
    *,
    account_id: str,
    referral_code: str,
    check: CancelCheck,
    protect: Callable[[str], str] | None,
    names: NameBank | None,
) -> dict[str, Any] | None:
    payload = client.get_json("/api/auth/me")
    if error_code(payload) == "WALLET_UNCLAIMED":
        claimed = client.post_json("/api/auth/wallet/claim", {})
        if isinstance(claimed, dict) and claimed.get("success") is False:
            raise SoftError("wallet_claim", "Не удалось закрепить кошелёк за кабинетом")
        payload = client.get_json("/api/auth/me")
    user = parse_me(payload)
    if user is None:
        return None
    check()
    complete_profile(
        client,
        account_id=account_id,
        check=check,
        referral_code=referral_code,
        existing=user,
        protect=protect,
        names=names,
    )
    payload = client.get_json("/api/auth/me")
    return parse_me(payload)


def _access_token(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    session = payload.get("session") if isinstance(payload.get("session"), dict) else payload
    if isinstance(session, dict):
        token = str(session.get("access_token") or payload.get("access_token") or "").strip()
        return token
    return str(payload.get("access_token") or "").strip()


def _is_captcha_error(payload: Any, status: int = 0) -> bool:
    if status == 403:
        return True
    code = error_code(payload).lower()
    if code in {"http_403", "captcha_failed", "captcha_unavailable"}:
        return True
    blob = f"{code} {error_message(payload)}".lower()
    if isinstance(payload, dict):
        blob += " " + str(payload.get("error") or "")
        blob += " " + str(payload.get("error_description") or "")
        blob += " " + str(payload.get("msg") or "")
        blob += " " + str(payload.get("code") or "")
    return "captcha" in blob.lower()


def _supabase_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_ANON,
        "Authorization": f"Bearer {SUPABASE_ANON}",
        "Origin": ORIGIN,
        "Referer": f"{ORIGIN}/live",
        "Sec-Fetch-Site": "cross-site",
    }
