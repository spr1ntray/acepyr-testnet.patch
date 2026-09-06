from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass

from .config import RunConfig

CancelCheck = Callable[[], None]


@dataclass(frozen=True)
class Tempo:
    name: str
    start: tuple[int, int]
    nav: tuple[int, int]
    think: tuple[int, int]
    action: tuple[int, int]
    api: tuple[int, int]
    long_chance: float
    long_ms: tuple[int, int]


TEMPOS = {
    "slow": Tempo("slow", (2200, 7000), (900, 3400), (600, 2400), (400, 1800), (90, 480), 0.22, (4500, 12000)),
    "steady": Tempo("steady", (900, 3200), (450, 1900), (280, 1300), (180, 950), (50, 300), 0.10, (2800, 8000)),
    "fast": Tempo("fast", (280, 1300), (220, 950), (140, 750), (70, 420), (30, 170), 0.04, (1600, 4200)),
    "bursty": Tempo("bursty", (400, 3800), (160, 2600), (80, 2100), (40, 1500), (20, 520), 0.15, (3200, 10000)),
}

_STYLE_TEMPO = {
    "cautious": ("slow", "steady"),
    "confident": ("steady", "slow"),
    "mixed": ("steady", "bursty"),
    "momentum": ("fast", "steady"),
    "crowd": ("steady", "bursty"),
    "crazy": ("fast", "bursty"),
}


def tempo_for(style: str, seed: int) -> Tempo:
    names = _STYLE_TEMPO.get(style, ("steady", "bursty"))
    pick = names[seed % len(names)]
    # slight mix so two cautious accounts are not clones
    if (seed // 7) % 11 == 0:
        pick = ("slow", "steady", "fast", "bursty")[seed % 4]
    return TEMPOS[pick]


def sleep_seconds(seconds: float, check: CancelCheck, rng: random.Random | None = None) -> None:
    ms = int(max(0.0, float(seconds)) * 1000)
    sleep_ms(ms, ms, check, rng)


def sleep_ms(low: int, high: int, check: CancelCheck, rng: random.Random | None = None) -> None:
    roller = rng or random
    left, right = (int(low), int(high)) if high >= low else (int(high), int(low))
    left = max(0, left)
    right = max(left, right)
    if right == left:
        delay = left / 1000.0
    else:
        delay = roller.triangular(left, right, left + (right - left) * 0.38) / 1000.0
    deadline = time.monotonic() + delay
    while True:
        check()
        remain = deadline - time.monotonic()
        if remain <= 0:
            return
        time.sleep(min(0.2, remain))


def wait_span(span: tuple[int, int], check: CancelCheck, rng: random.Random | None = None) -> None:
    sleep_ms(span[0], span[1], check, rng)


def start_delay(style: str, check: CancelCheck, rng: random.Random | None = None, tempo: Tempo | None = None) -> None:
    roller = rng or random
    chosen = tempo or TEMPOS["steady"]
    wait_span(chosen.start, check, roller)
    maybe_long(chosen, check, roller)


def maybe_long(tempo: Tempo, check: CancelCheck, rng: random.Random | None = None) -> None:
    roller = rng or random
    if roller.random() < tempo.long_chance:
        wait_span(tempo.long_ms, check, roller)


def between_pages(tempo: Tempo, check: CancelCheck, rng: random.Random | None = None) -> None:
    roller = rng or random
    wait_span(tempo.nav, check, roller)
    wait_span(tempo.think, check, roller)


def between_api(tempo: Tempo, check: CancelCheck, rng: random.Random | None = None) -> None:
    wait_span(tempo.api, check, rng)


def between_quote_and_trade(tempo: Tempo, check: CancelCheck, rng: random.Random | None = None) -> None:
    wait_span(tempo.action, check, rng)


def between_bets(
    cfg: RunConfig,
    tempo: Tempo,
    check: CancelCheck,
    rng: random.Random | None = None,
    *,
    allow_long: bool = True,
) -> None:
    roller = rng or random
    low, high = cfg.pause_from_ms, cfg.pause_to_ms
    if high < low:
        low, high = high, low
    pad = roller.randint(0, max(200, int((high - low) * 0.7) + tempo.action[0] // 2))
    sleep_ms(low, high + pad, check, roller)
    if allow_long:
        maybe_long(tempo, check, roller)
