from __future__ import annotations

from typing import Any

from .config import SLIPPAGE


def unwrap(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    if payload.get("success") is False:
        return payload
    if "data" in payload and payload.get("success") is True:
        return payload.get("data")
    return payload


def error_code(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    err = payload.get("error")
    if isinstance(err, dict):
        return str(err.get("code") or "")
    if isinstance(err, str):
        return err
    return str(payload.get("code") or "")


def error_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    err = payload.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or "")
    if isinstance(err, str):
        return err
    return str(payload.get("message") or "")


def parse_me(payload: Any) -> dict[str, Any] | None:
    body = unwrap(payload)
    if not isinstance(body, dict):
        return None
    user = body.get("user") if isinstance(body.get("user"), dict) else body
    if not isinstance(user, dict):
        return None
    user_id = str(user.get("id") or "").strip()
    if not user_id:
        return None
    return user


def parse_balance(payload: Any) -> float:
    body = unwrap(payload)
    if isinstance(body, dict):
        raw = body.get("balance")
    else:
        raw = body
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def parse_portfolio_count(payload: Any) -> int:
    body = unwrap(payload)
    if isinstance(body, list):
        return len(body)
    if isinstance(body, dict):
        for key in ("positions", "items", "markets", "data"):
            rows = body.get(key)
            if isinstance(rows, list):
                return len(rows)
        if isinstance(body.get("count"), int):
            return int(body["count"])
    return 0


def quote_max_cost(amount: float, quote: dict[str, Any] | None) -> float:
    data = unwrap(quote) if isinstance(quote, dict) else quote
    total = None
    if isinstance(data, dict):
        raw = data.get("totalCost")
        if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw > 0:
            total = float(raw)
    if total is None:
        total = float(amount)
    return round(total * SLIPPAGE, 8)


def quote_is_valid(quote: dict[str, Any] | None) -> bool:
    data = unwrap(quote) if isinstance(quote, dict) else quote
    if not isinstance(data, dict):
        return False
    if data.get("isValid") is False:
        return False
    return True


def trade_ok(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("success") is True:
        return True
    data = payload.get("data")
    if isinstance(data, dict) and data.get("success") is True:
        return True
    return bool(payload.get("transactionId"))
