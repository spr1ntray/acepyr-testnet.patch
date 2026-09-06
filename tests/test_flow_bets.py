from __future__ import annotations

import random

from plugin.ace_bot.config import RunConfig
from plugin.ace_bot.flow import next_wait_seconds, place_bets
from plugin.ace_bot.strategy import Candidate, persona_for


def _cand(prob: float, seconds: float = 80) -> Candidate:
    return Candidate(
        market_id="m1",
        slug="btc-up-or-down",
        symbol="BTC",
        title="BTC Up or Down",
        outcome="down",
        probability=prob,
        seconds_left=seconds,
    )


def test_next_wait_seconds_caps_at_budget() -> None:
    pool = [_cand(0.5, seconds=200)]
    assert next_wait_seconds(pool, 300) == 204.0
    assert next_wait_seconds(pool, 30) == 30.0
    assert next_wait_seconds([], 300) == 15.0
    assert next_wait_seconds(pool, 0) == 0.0


def test_place_bets_waits_then_takes_any(monkeypatch) -> None:
    waited: list[float] = []
    loads = {"n": 0}

    def fake_load(api, *, persona, check, rng):
        loads["n"] += 1
        return [_cand(0.55, seconds=40)]

    def fake_trade(api, pick, amount, check, *, persona, rng):
        return True, float(amount), ""

    monkeypatch.setattr("plugin.ace_bot.flow.load_candidates", fake_load)
    monkeypatch.setattr("plugin.ace_bot.flow.sleep_seconds", lambda seconds, check, rng=None: waited.append(seconds))
    monkeypatch.setattr("plugin.ace_bot.flow._one_trade", fake_trade)
    monkeypatch.setattr("plugin.ace_bot.flow.between_bets", lambda *args, **kwargs: None)
    monkeypatch.setattr("plugin.ace_bot.flow.bets_this_run", lambda cfg, rng=None: 1)

    persona = persona_for("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    persona = persona.__class__(
        style="cautious",
        extras=persona.extras,
        assets=persona.assets,
        scroll=persona.scroll,
        tempo=persona.tempo,
    )
    placed, cash, note = place_bets(
        api=object(),
        persona=persona,
        cfg=RunConfig(bets_from=1, bets_to=1, bet_from=10, bet_to=10),
        balance=100,
        check=lambda: None,
        rng=random.Random(1),
    )
    assert waited
    assert waited[0] == 44.0
    assert placed == 1
    assert note == ""
    assert cash < 100
    assert loads["n"] >= 2
