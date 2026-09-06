from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import MIN_SECONDS_LEFT
from .strategy import Candidate


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def parse_server_now(payload: dict[str, Any] | None) -> float:
    text = str((payload or {}).get("serverNow") or "")
    if text:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return datetime.now(timezone.utc).timestamp()


def seconds_left(window_end: str | None, server_now: float) -> float:
    if not window_end:
        return 0.0
    try:
        end = datetime.fromisoformat(window_end.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
    return end - server_now


def parse_five_min(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = (payload or {}).get("data")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    now = parse_server_now(payload)
    for row in rows:
        if not isinstance(row, dict):
            continue
        active = row.get("active")
        if not isinstance(active, dict):
            continue
        market_id = str(active.get("marketId") or "").strip()
        if not market_id:
            continue
        left = seconds_left(str(active.get("windowEnd") or ""), now)
        out.append(
            {
                "market_id": market_id,
                "slug": str(active.get("slug") or ""),
                "symbol": str(active.get("symbol") or "").upper(),
                "title": str(active.get("title") or ""),
                "status": str(active.get("status") or ""),
                "seconds_left": left,
                "price_to_beat": _as_float(active.get("priceToBeat")),
                "current_price": _as_float(active.get("currentPrice")),
                "up_probability": _as_float(active.get("upProbability")),
            }
        )
    return out


def _price_map(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data") if "data" in payload else payload.get("prices")
    if not isinstance(data, dict):
        data = payload.get("prices")
    if not isinstance(data, dict):
        return {}
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def probability_of(prices: dict[str, dict[str, Any]], outcome: str) -> float | None:
    row = prices.get(outcome) or {}
    value = _as_float(row.get("impliedProbability"))
    if value is None:
        value = _as_float(row.get("price"))
    return value


def candidates_from_market(
    market: dict[str, Any],
    prices: dict[str, dict[str, Any]],
    *,
    crowd_side: str | None = None,
) -> list[Candidate]:
    if float(market.get("seconds_left") or 0) < MIN_SECONDS_LEFT:
        return []
    if str(market.get("status") or "") not in {"", "active"}:
        return []
    found: list[Candidate] = []
    for outcome in ("up", "down"):
        prob = probability_of(prices, outcome)
        if prob is None:
            if outcome == "up":
                prob = _as_float(market.get("up_probability"))
            elif outcome == "down" and _as_float(market.get("up_probability")) is not None:
                up = float(market["up_probability"])
                prob = max(0.0, min(1.0, 1.0 - up))
        if prob is None:
            continue
        found.append(
            Candidate(
                market_id=str(market["market_id"]),
                slug=str(market.get("slug") or ""),
                symbol=str(market.get("symbol") or ""),
                title=str(market.get("title") or ""),
                outcome=outcome,
                probability=float(prob),
                seconds_left=float(market.get("seconds_left") or 0),
                price_to_beat=_as_float(market.get("price_to_beat")),
                current_price=_as_float(market.get("current_price")),
                crowd_side=crowd_side,
            )
        )
    return found


def crowd_side_from_plays(plays: list[dict[str, Any]], market_id: str) -> str | None:
    scores = {"up": 0.0, "down": 0.0}
    for row in plays:
        if not isinstance(row, dict):
            continue
        if str(row.get("marketId") or "") != market_id:
            continue
        if str(row.get("action") or "") != "bought":
            continue
        label = str(row.get("optionLabel") or row.get("side") or "").lower()
        side = None
        if label in {"up", "yes"}:
            side = "up"
        elif label in {"down", "no"}:
            side = "down"
        if side is None:
            continue
        amount = _as_float(row.get("value")) or 1.0
        scores[side] += max(0.0, amount)
    if scores["up"] <= 0 and scores["down"] <= 0:
        return None
    if scores["up"] == scores["down"]:
        return None
    return "up" if scores["up"] > scores["down"] else "down"


def parse_plays(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = (payload or {}).get("data")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def parse_prices(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return _price_map(payload)
