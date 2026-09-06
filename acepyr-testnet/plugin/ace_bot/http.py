from __future__ import annotations

import time
from typing import Any

from .config import ORIGIN
from .errors import BlockedError, SoftError
from .identity import BrowserIdentity
from .parse import error_code
from .utils import normalize_proxy

_IMPERSONATE_FALLBACKS = ("chrome136", "chrome131", "chrome124", "chrome120")
_RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}
_RETRY_ATTEMPTS = 5


def assert_api_path(path: str) -> str:
    text = (path or "").strip()
    if not text.startswith("/api/") or ".." in text or "://" in text:
        raise SoftError("unsafe_endpoint", "Внутренний путь API отклонён")
    return text


def _network_error(exc: BaseException) -> SoftError:
    text = str(exc).lower()
    if "proxy" in text:
        return SoftError("proxy_error", "Прокси не пускает запрос")
    if "timeout" in text or "timed out" in text:
        return SoftError("http_timeout", "Сайт не ответил вовремя")
    if "ssl" in text or "tls" in text:
        return SoftError("tls_error", "Не удалось установить защищённое соединение")
    return SoftError("http_network", "Сайт не ответил. Повторите запуск")


class AceClient:
    def __init__(self, identity: BrowserIdentity, proxy: str | None, timeout: int = 45) -> None:
        self.identity = identity
        self.timeout = timeout
        self._bearer = ""
        try:
            proxy_url = normalize_proxy(proxy)
        except ValueError as exc:
            raise SoftError("invalid_proxy", "Неверный формат прокси") from exc
        self.proxy_url = proxy_url
        self.session, self.impersonate = _open_session(identity.impersonate, proxy_url, timeout)
        self.session.headers.clear()
        self.session.headers.update(self._headers())

    def set_bearer(self, token: str) -> None:
        self._bearer = (token or "").strip()
        self.session.headers.update(self._headers())

    def close(self) -> None:
        closer = getattr(self.session, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:
                pass

    def _headers(
        self,
        extra: dict[str, str] | None = None,
        *,
        navigate: bool = False,
        origin: bool = False,
    ) -> dict[str, str]:
        headers = {
            "sec-ch-ua": self.identity.sec_ch_ua,
            "sec-ch-ua-mobile": self.identity.sec_ch_ua_mobile,
            "sec-ch-ua-platform": self.identity.sec_ch_ua_platform,
            "User-Agent": self.identity.user_agent,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
                if navigate
                else "*/*"
            ),
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate" if navigate else "cors",
            "Sec-Fetch-Dest": "document" if navigate else "empty",
            "Referer": f"{ORIGIN}/live",
            "Accept-Language": self.identity.accept_language,
            "Priority": "u=0, i" if navigate else "u=1, i",
        }
        if navigate:
            headers["Upgrade-Insecure-Requests"] = "1"
        if origin:
            headers["Origin"] = ORIGIN
        if self._bearer:
            headers["Authorization"] = f"Bearer {self._bearer}"
        if extra:
            headers.update(extra)
        return headers

    def request_url(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        merged = self._headers(headers, origin=json_body is not None)
        kwargs: dict[str, Any] = {"headers": merged}
        if json_body is not None:
            merged["Content-Type"] = "application/json"
            kwargs["json"] = json_body
        resp = self._request(method, url, **kwargs)
        status = int(getattr(resp, "status_code", 0) or 0)
        try:
            data = resp.json() if getattr(resp, "content", b"") else {}
        except Exception:
            data = {}
        return status, data

    def get_text(self, path: str) -> str:
        url = path if path.startswith("http") else ORIGIN + path
        headers = self._headers(navigate=True)
        resp = self._request("GET", url, headers=headers, allow_redirects=True)
        text = getattr(resp, "text", None)
        if isinstance(text, str):
            return text
        content = getattr(resp, "content", b"")
        if isinstance(content, (bytes, bytearray)):
            return content.decode("utf-8", "replace")
        return ""

    def get_json(self, path: str) -> Any:
        return self._json("GET", path, None)

    def post_json(self, path: str, body: dict[str, Any] | None) -> Any:
        return self._json("POST", path, body or {})

    def put_json(
        self,
        path: str,
        body: dict[str, Any] | None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        return self._json("PUT", path, body or {}, extra_headers)

    def _json(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        path = assert_api_path(path)
        url = ORIGIN + path
        mutating = method in {"POST", "PUT", "PATCH"}
        headers = self._headers(extra_headers, origin=mutating)
        kwargs: dict[str, Any] = {"headers": headers}
        if mutating:
            headers["Content-Type"] = "application/json"
            kwargs["json"] = body or {}
        resp = self._request(method, url, **kwargs)
        status = int(getattr(resp, "status_code", 0) or 0)
        try:
            data = resp.json() if getattr(resp, "content", b"") else {}
        except Exception:
            data = {}
        if status == 401 and error_code(data) == "WALLET_UNCLAIMED":
            return data
        if status == 401 or error_code(data) == "AUTH_TOKEN_MISSING":
            raise BlockedError("not_logged_in", "Acepyr не пустил в кабинет")
        if status == 429:
            raise SoftError("rate_limit", "Acepyr просит подождать")
        if status >= 500:
            raise SoftError("acepyr_unavailable", "Acepyr временно не отвечает")
        if status >= 400:
            return data if data else {"success": False, "error": {"code": f"http_{status}"}}
        return data

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        last: Exception | None = None
        kwargs.setdefault("timeout", self.timeout)
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                resp = self.session.request(method, url, **kwargs)
            except Exception as exc:
                last = exc
                if attempt + 1 >= _RETRY_ATTEMPTS:
                    break
                time.sleep(0.8 * (attempt + 1))
                continue
            status = int(getattr(resp, "status_code", 0) or 0)
            if status in _RETRY_STATUSES and attempt + 1 < _RETRY_ATTEMPTS:
                time.sleep(0.8 * (attempt + 1))
                continue
            return resp
        raise _network_error(last or RuntimeError("http_network")) from last


def _open_session(preferred: str, proxy_url: str | None, timeout: int) -> tuple[Any, str]:
    try:
        from curl_cffi import requests as cf
    except Exception as exc:  # pragma: no cover
        raise SoftError("tls_runtime", "Нет библиотеки Chrome TLS") from exc

    last: Exception | None = None
    seen: list[str] = []
    for name in (preferred, *_IMPERSONATE_FALLBACKS):
        if name in seen:
            continue
        seen.append(name)
        try:
            session = cf.Session(impersonate=name, timeout=timeout)
            if hasattr(session, "trust_env"):
                session.trust_env = False
            if proxy_url:
                session.proxies = {"http": proxy_url, "https": proxy_url}
            return session, name
        except Exception as exc:
            last = exc
    raise SoftError("tls_impersonate", "Не удалось включить Chrome TLS") from last
