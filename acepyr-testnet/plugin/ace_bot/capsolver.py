from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any
from urllib.parse import unquote, urlparse

import requests

from .errors import SoftError

CREATE_URL = "https://api.capsolver.com/createTask"
RESULT_URL = "https://api.capsolver.com/getTaskResult"

CancelCheck = Callable[[], None]


def _post(url: str, payload: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise SoftError("capsolver_network", "Не удалось связаться с Capsolver") from exc
    try:
        data = resp.json()
    except Exception:
        data = {}
    if isinstance(data, dict) and data.get("errorId"):
        raise SoftError("capsolver_error", "Capsolver не принял задачу")
    if resp.status_code >= 400:
        raise SoftError("capsolver_http", "Capsolver вернул ошибку")
    return data if isinstance(data, dict) else {}


def capsolver_proxy(proxy: str | None) -> str:
    raw = (proxy or "").strip()
    if not raw:
        return ""
    text = raw if "://" in raw or "@" in raw else ""
    if text:
        parsed = urlparse(text if "://" in text else f"http://{text}")
        host = parsed.hostname or ""
        port = parsed.port
        if host and port:
            user = unquote(parsed.username or "")
            password = unquote(parsed.password or "")
            if user:
                return f"{host}:{port}:{user}:{password}"
            return f"{host}:{port}"
    packed = raw.replace("http://", "").replace("https://", "")
    return packed


def _token_from(payload: dict[str, Any]) -> str:
    solution = payload.get("solution") if isinstance(payload.get("solution"), dict) else {}
    token = solution.get("token") or solution.get("gRecaptchaResponse") or ""
    return str(token).strip()


def solve_turnstile(
    api_key: str,
    *,
    site_key: str,
    page_url: str,
    proxy: str | None = None,
    action: str = "",
    timeout_seconds: int = 180,
    check: CancelCheck | None = None,
) -> str:
    key = (api_key or "").strip()
    if len(key) < 4:
        raise SoftError("capsolver_missing", "Не задан ключ Capsolver")
    waiter = check or (lambda: None)
    meta = {"action": action} if action else None
    base: dict[str, Any] = {
        "websiteURL": page_url,
        "websiteKey": site_key,
    }
    if meta:
        base["metadata"] = meta
    tasks: list[dict[str, Any]] = [{"type": "AntiTurnstileTaskProxyLess", **base}]
    packed = capsolver_proxy(proxy)
    if packed:
        tasks.insert(0, {"type": "AntiTurnstileTask", **base, "proxy": packed})
    last: Exception | None = None
    for task in tasks:
        waiter()
        try:
            created = _post(CREATE_URL, {"clientKey": key, "task": task})
            ready = _token_from(created)
            if created.get("status") == "ready" and ready:
                return ready
            task_id = created.get("taskId")
            if not task_id:
                last = SoftError("capsolver_error", "Capsolver не создал задачу")
                continue
            return _poll(key, str(task_id), timeout_seconds=timeout_seconds, check=waiter)
        except SoftError as exc:
            last = exc
            continue
    raise last or SoftError("capsolver_error", "Не удалось пройти Turnstile")


def _poll(
    api_key: str,
    task_id: str,
    *,
    timeout_seconds: int,
    check: CancelCheck,
) -> str:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        check()
        time.sleep(3)
        check()
        data = _post(RESULT_URL, {"clientKey": api_key, "taskId": task_id})
        status = data.get("status")
        if status == "ready":
            token = _token_from(data)
            if not token:
                raise SoftError("capsolver_empty", "Turnstile вернулся пустым")
            return token
        if status and status not in {"idle", "processing"}:
            raise SoftError("capsolver_error", "Turnstile не прошёл")
    raise SoftError("capsolver_timeout", "Turnstile не успел решиться")
