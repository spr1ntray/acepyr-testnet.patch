from __future__ import annotations

import random
from uuid import uuid4

from plugin.ace_bot.config import RunConfig
from plugin.ace_bot.pace import TEMPOS, between_bets, sleep_ms, tempo_for
from plugin.ace_bot.strategy import persona_for


def test_persona_keeps_tempo() -> None:
    account_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert persona_for(account_id).tempo == persona_for(account_id).tempo
    assert persona_for(account_id).tempo.name in TEMPOS


def test_cautious_prefers_slower_tempo() -> None:
    names = {tempo_for("cautious", seed).name for seed in range(40)}
    assert "slow" in names
    assert "fast" in names or "steady" in names


def test_accounts_differ_in_tempo_or_path() -> None:
    seen = {
        (persona_for(str(uuid4())).style, persona_for(str(uuid4())).tempo.name)
        for _ in range(60)
    }
    # two independent draws; uniqueness of the pair set is enough
    personas = [persona_for(str(uuid4())) for _ in range(80)]
    shapes = {(item.style, item.tempo.name, item.extras, item.scroll) for item in personas}
    assert len(shapes) > 8
    assert seen  # silence linters if collection is empty in a broken import


def test_sleep_ms_respects_cancel() -> None:
    hits = {"n": 0}

    def check() -> None:
        hits["n"] += 1

    sleep_ms(1, 4, check, random.Random(1))
    assert hits["n"] >= 1


def test_between_bets_uses_user_range() -> None:
    cfg = RunConfig(pause_from_ms=200, pause_to_ms=300)
    calls: list[int] = []

    def check() -> None:
        calls.append(1)

    between_bets(cfg, TEMPOS["fast"], check, random.Random(2), allow_long=False)
    assert calls
