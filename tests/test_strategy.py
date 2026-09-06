from __future__ import annotations

from collections import Counter
from uuid import uuid4

from plugin.ace_bot.config import RunConfig
from plugin.ace_bot.strategy import (
    Candidate,
    assign_strategy,
    filter_candidates,
    persona_for,
    pick_amount,
    pick_candidate,
)


def _cand(outcome: str, prob: float, symbol: str = "BTC", seconds: float = 120, **extra) -> Candidate:
    return Candidate(
        market_id="m1" if symbol == "BTC" else f"m-{symbol}-{outcome}",
        slug=f"{symbol.lower()}-up-or-down",
        symbol=symbol,
        title=f"{symbol} Up or Down",
        outcome=outcome,
        probability=prob,
        seconds_left=seconds,
        **extra,
    )


def test_strategy_shares_match_contract() -> None:
    counts: Counter[str] = Counter()
    for _ in range(6000):
        counts[assign_strategy(str(uuid4()))] += 1
    total = sum(counts.values())
    shares = {name: counts[name] / total for name in ("confident", "cautious", "mixed", "momentum", "crowd", "crazy")}
    assert 0.24 < shares["confident"] < 0.32
    assert 0.18 < shares["cautious"] < 0.26
    assert 0.14 < shares["mixed"] < 0.22
    assert 0.10 < shares["momentum"] < 0.18
    assert 0.08 < shares["crowd"] < 0.16
    assert 0.03 < shares["crazy"] < 0.10


def test_same_account_keeps_strategy() -> None:
    account_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert assign_strategy(account_id) == assign_strategy(account_id)
    assert persona_for(account_id).style == assign_strategy(account_id)
    assert persona_for(account_id).extras == persona_for(account_id).extras


def test_confident_skips_longshots() -> None:
    pool = [_cand("down", 0.91), _cand("up", 0.12, symbol="ETH")]
    kept = filter_candidates("confident", pool, spicy=False)
    assert [item.symbol for item in kept] == ["BTC"]


def test_cautious_needs_ninety() -> None:
    pool = [_cand("down", 0.88), _cand("down", 0.93, symbol="ETH")]
    kept = filter_candidates("cautious", pool, spicy=False)
    assert [item.symbol for item in kept] == ["ETH"]


def test_momentum_follows_price() -> None:
    up = _cand("up", 0.70, current_price=101.0, price_to_beat=100.0)
    down = _cand("down", 0.70, symbol="ETH", current_price=101.0, price_to_beat=100.0)
    kept = filter_candidates("momentum", [up, down], spicy=False)
    assert [item.outcome for item in kept] == ["up"]


def test_crowd_needs_matching_side() -> None:
    yes = _cand("down", 0.81, crowd_side="down")
    no = _cand("up", 0.81, symbol="ETH", crowd_side="down")
    kept = filter_candidates("crowd", [yes, no], spicy=False)
    assert [item.outcome for item in kept] == ["down"]


def test_crazy_keeps_everything_alive() -> None:
    pool = [_cand("up", 0.91), _cand("down", 0.08, symbol="ETH")]
    assert len(filter_candidates("crazy", pool, spicy=False)) == 2


def test_stale_window_is_dropped() -> None:
    pool = [_cand("down", 0.95, seconds=10)]
    assert filter_candidates("confident", pool, spicy=False) == []


def test_cautious_amount_stays_in_lower_band() -> None:
    cfg = RunConfig(bet_from=100, bet_to=400)
    amounts = [pick_amount("cautious", cfg, 2000) for _ in range(80)]
    typical = [amount for amount in amounts if amount <= 220]
    assert len(typical) >= 60


def test_pick_does_not_repeat_used() -> None:
    pool = [_cand("down", 0.95)]
    first, _ = pick_candidate("confident", pool, set())
    second, _ = pick_candidate("confident", pool, {("m1", "down")})
    assert first is not None
    assert second is None


def test_pick_fallback_takes_any_live() -> None:
    pool = [_cand("down", 0.40)]
    missed, _ = pick_candidate("cautious", pool, set(), rng=__import__("random").Random(0))
    taken, _ = pick_candidate("cautious", pool, set(), rng=__import__("random").Random(0), any_live=True)
    assert missed is None
    assert taken is not None
    assert taken.probability == 0.40
