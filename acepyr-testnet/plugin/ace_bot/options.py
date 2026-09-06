from __future__ import annotations

from typing import Any

from .config import BETS_MAX, RunConfig


def integer_option(options: dict[str, Any], name: str, default: int, low: int, high: int) -> int:
    value = options.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name}_invalid")
    if not low <= value <= high:
        raise ValueError(f"{name}_range")
    return value


def farm_config(options: dict[str, Any]) -> RunConfig:
    bets_from = integer_option(options, "bets_from", 2, 1, BETS_MAX)
    bets_to = integer_option(options, "bets_to", 4, 1, BETS_MAX)
    if bets_from > bets_to:
        raise ValueError("bets_range")
    bet_from = integer_option(options, "bet_from", 10, 5, 2000)
    bet_to = integer_option(options, "bet_to", 100, 5, 2000)
    if bet_from > bet_to:
        raise ValueError("bet_range")
    pause_from = integer_option(options, "pause_from_ms", 800, 200, 8000)
    pause_to = integer_option(options, "pause_to_ms", 2400, 200, 8000)
    if pause_from > pause_to:
        raise ValueError("pause_range")
    return RunConfig(
        bets_from=bets_from,
        bets_to=bets_to,
        bet_from=bet_from,
        bet_to=bet_to,
        pause_from_ms=pause_from,
        pause_to_ms=pause_to,
    )
