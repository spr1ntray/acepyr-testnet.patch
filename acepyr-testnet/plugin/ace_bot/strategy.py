from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from .config import (
    ASSET_ORDER,
    EXTRA_PATHS,
    MIN_BET,
    MIN_SECONDS_LEFT,
    SPICE_CHANCE,
    STRATEGY_RANGES,
    RunConfig,
)
from .pace import Tempo, tempo_for


@dataclass(frozen=True)
class Candidate:
    market_id: str
    slug: str
    symbol: str
    title: str
    outcome: str
    probability: float
    seconds_left: float
    price_to_beat: float | None = None
    current_price: float | None = None
    crowd_side: str | None = None


@dataclass(frozen=True)
class Persona:
    style: str
    extras: tuple[str, ...]
    assets: tuple[str, ...]
    scroll: bool
    tempo: Tempo


def assign_strategy(account_id: str) -> str:
    digest = hashlib.sha256(f"acepyr-strategy:{account_id}".encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    for name, start, end in STRATEGY_RANGES:
        if start <= bucket < end:
            return name
    return "crazy"


def persona_for(account_id: str) -> Persona:
    style = assign_strategy(account_id)
    seed = int(hashlib.sha256(f"acepyr-persona:{account_id}".encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed)
    extras = list(EXTRA_PATHS)
    rng.shuffle(extras)
    assets = list(ASSET_ORDER)
    rng.shuffle(assets)
    if style in {"confident", "cautious", "momentum"}:
        assets = ["BTC", "ETH"] + [item for item in assets if item not in {"BTC", "ETH"}]
    extra_count = 1 + (seed % 3)
    return Persona(
        style=style,
        extras=tuple(extras[:extra_count]),
        assets=tuple(assets),
        scroll=bool(seed % 2),
        tempo=tempo_for(style, seed),
    )


def spice_roll(style: str, rng: random.Random | None = None) -> bool:
    chance = SPICE_CHANCE.get(style, 0.0)
    roller = rng or random
    return chance > 0 and roller.random() < chance


def _alive(item: Candidate) -> bool:
    return item.seconds_left >= MIN_SECONDS_LEFT and 0.01 <= item.probability <= 0.99


def filter_candidates(style: str, pool: list[Candidate], *, spicy: bool) -> list[Candidate]:
    live = [item for item in pool if _alive(item)]
    if style == "crazy" or (spicy and style == "crowd"):
        return list(live)
    if spicy and style == "confident":
        return [item for item in live if 0.08 <= item.probability <= 0.30]
    if spicy and style == "cautious":
        return [item for item in live if 0.50 <= item.probability <= 0.72]
    if spicy and style == "mixed":
        return [item for item in live if 0.12 <= item.probability < 0.28]
    if spicy and style == "momentum":
        return [item for item in live if item.probability >= 0.55]
    if style == "confident":
        return [item for item in live if item.probability >= 0.80]
    if style == "cautious":
        return [item for item in live if item.probability >= 0.90]
    if style == "mixed":
        favorites = [item for item in live if item.probability >= 0.80]
        mid = [item for item in live if 0.55 <= item.probability <= 0.75]
        return favorites + mid
    if style == "momentum":
        return [item for item in live if _momentum_ok(item) and item.probability >= 0.62]
    if style == "crowd":
        marked = [
            item
            for item in live
            if item.crowd_side == item.outcome and item.probability >= 0.70
        ]
        return marked
    return list(live)


def _momentum_ok(item: Candidate) -> bool:
    if item.price_to_beat is None or item.current_price is None:
        return False
    going_up = item.current_price > item.price_to_beat
    going_down = item.current_price < item.price_to_beat
    if item.outcome == "up":
        return going_up
    if item.outcome == "down":
        return going_down
    return False


def pick_candidate(
    style: str,
    pool: list[Candidate],
    used: set[tuple[str, str]],
    rng: random.Random | None = None,
    *,
    preferred_assets: tuple[str, ...] = (),
    any_live: bool = False,
) -> tuple[Candidate | None, bool]:
    roller = rng or random
    spicy = spice_roll(style, roller)
    filtered = [
        item
        for item in filter_candidates(style, pool, spicy=spicy)
        if (item.market_id, item.outcome) not in used
    ]
    if not filtered and spicy:
        filtered = [
            item
            for item in filter_candidates(style, pool, spicy=False)
            if (item.market_id, item.outcome) not in used
        ]
        spicy = False
    if not filtered and any_live:
        filtered = [
            item
            for item in pool
            if _alive(item) and (item.market_id, item.outcome) not in used
        ]
    if not filtered:
        return None, False
    if preferred_assets:
        ranked: list[Candidate] = []
        for symbol in preferred_assets:
            ranked.extend(item for item in filtered if item.symbol == symbol)
        ranked.extend(item for item in filtered if item not in ranked)
        filtered = ranked or filtered
    if style == "mixed" and not spicy:
        favorites = [item for item in filtered if item.probability >= 0.80]
        mid = [item for item in filtered if 0.55 <= item.probability <= 0.75]
        bucket = favorites if favorites and (not mid or roller.random() < 0.55) else (mid or filtered)
        return roller.choice(bucket), spicy
    if preferred_assets and filtered:
        top = [item for item in filtered if item.symbol == preferred_assets[0]]
        if top and roller.random() < 0.55:
            return roller.choice(top), spicy
    return roller.choice(filtered), spicy


def pick_amount(style: str, cfg: RunConfig, balance: float, rng: random.Random | None = None) -> int:
    roller = rng or random
    low = int(cfg.bet_from)
    high = int(cfg.bet_to)
    if high < low:
        low, high = high, low
    if style == "cautious":
        high = low + max(1, (high - low) // 3)
    if style == "crazy" and roller.random() < 0.25:
        share = roller.uniform(0.20, 0.55)
        amount = max(MIN_BET, min(int(balance), int(balance * share)))
        return int(min(amount, int(balance)))
    amount = roller.randint(low, max(low, high))
    if style == "cautious" and spice_roll(style, roller):
        amount = min(int(balance), int(amount * roller.uniform(1.3, 1.8)))
    return int(min(amount, max(0, int(balance))))


def bets_this_run(cfg: RunConfig, rng: random.Random | None = None) -> int:
    roller = rng or random
    low, high = cfg.bets_from, cfg.bets_to
    if high < low:
        low, high = high, low
    return roller.randint(low, high)
