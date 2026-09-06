from __future__ import annotations

import random
from collections.abc import Callable
from typing import Any

from .config import MARKET_WAIT_SECONDS, MIN_BET, MIN_SECONDS_LEFT, ORIGIN, TRADE_RETRIES, RunConfig
from .copy import NO_FUNDS, NO_MARKET, NOT_LOGGED_IN, NEED_USERNAME, WINDOW_CLOSED
from .errors import BlockedError, SoftError
from .http import AceClient
from .markets import (
    candidates_from_market,
    crowd_side_from_plays,
    parse_five_min,
    parse_plays,
    parse_prices,
)
from .pace import between_api, between_bets, between_quote_and_trade, between_pages, sleep_seconds
from .parse import parse_balance, parse_me, parse_portfolio_count, quote_is_valid, quote_max_cost, trade_ok
from .strategy import Candidate, Persona, bets_this_run, pick_amount, pick_candidate
from .wallet import already_linked, link_wallet

CancelCheck = Callable[[], None]


def snapshot(api: AceClient) -> dict[str, Any]:
    user = parse_me(api.get_json("/api/auth/me"))
    if user is None:
        raise BlockedError("not_logged_in", NOT_LOGGED_IN)
    if user.get("needsUsername") is True:
        raise BlockedError("need_username", NEED_USERNAME)
    balance = parse_balance(api.get_json("/api/economy/balance"))
    bets = parse_portfolio_count(api.get_json("/api/markets/user/portfolio"))
    return {
        "user": user,
        "username": str(user.get("username") or ""),
        "balance": balance,
        "bets": bets,
        "wallet_linked": bool(user.get("walletAddress") or user.get("walletCredentialAddress")),
    }


def warmup(api: AceClient, persona: Persona, check: CancelCheck, rng: random.Random) -> None:
    try:
        api.get_text("/live")
    except SoftError:
        pass
    between_pages(persona.tempo, check, rng)
    extras = list(persona.extras)
    rng.shuffle(extras)
    for extra in extras[: 1 + rng.randint(0, 1)]:
        check()
        try:
            api.get_text(extra)
        except SoftError:
            pass
        between_pages(persona.tempo, check, rng)
    _ = ORIGIN


def visit_faucet(api: AceClient, check: CancelCheck, rng: random.Random, persona: Persona) -> None:
    try:
        api.get_text("/faucet")
    except SoftError:
        pass
    between_api(persona.tempo, check, rng)
    try:
        api.get_json("/api/faucet/mine")
    except SoftError:
        return
    between_api(persona.tempo, check, rng)


def load_candidates(api: AceClient, *, persona: Persona, check: CancelCheck, rng: random.Random) -> list[Candidate]:
    five = api.get_json("/api/markets/5min?windows=1")
    between_api(persona.tempo, check, rng)
    markets = parse_five_min(five if isinstance(five, dict) else {})
    plays_payload = api.get_json("/api/activity/live-plays?limit=30")
    plays = parse_plays(plays_payload if isinstance(plays_payload, dict) else {})
    found: list[Candidate] = []
    for market in markets:
        if float(market.get("seconds_left") or 0) < MIN_SECONDS_LEFT:
            continue
        between_api(persona.tempo, check, rng)
        crowd = crowd_side_from_plays(plays, str(market["market_id"]))
        prices_raw = api.get_json(f"/api/markets/{market['market_id']}/prices")
        prices = parse_prices(prices_raw if isinstance(prices_raw, dict) else {})
        found.extend(candidates_from_market(market, prices, crowd_side=crowd))
    return found


def next_wait_seconds(pool: list[Candidate], budget: float) -> float:
    if budget <= 0:
        return 0.0
    left = [item.seconds_left for item in pool if item.seconds_left > 0]
    if not left:
        return min(budget, 15.0)
    return min(budget, max(8.0, min(max(left) + 4.0, float(MARKET_WAIT_SECONDS))))


def _take_pick(
    style: str,
    pool: list[Candidate],
    used: set[tuple[str, str]],
    rng: random.Random,
    assets: tuple[str, ...],
    *,
    any_live: bool,
) -> Candidate | None:
    pick, _spicy = pick_candidate(
        style,
        pool,
        used,
        rng,
        preferred_assets=assets,
        any_live=any_live,
    )
    return pick


def place_bets(
    api: AceClient,
    *,
    persona: Persona,
    cfg: RunConfig,
    balance: float,
    check: CancelCheck,
    rng: random.Random,
) -> tuple[int, float, str]:
    planned = bets_this_run(cfg, rng)
    cash = float(balance)
    placed = 0
    used: set[tuple[str, str]] = set()
    note = ""
    wait_left = float(MARKET_WAIT_SECONDS)
    for _ in range(planned):
        check()
        if cash < MIN_BET:
            note = NO_FUNDS
            break
        pool = load_candidates(api, persona=persona, check=check, rng=rng)
        pick = _take_pick(persona.style, pool, used, rng, persona.assets, any_live=False)
        if pick is None and wait_left > 0:
            pause = next_wait_seconds(pool, wait_left)
            sleep_seconds(pause, check, rng)
            wait_left = max(0.0, wait_left - pause)
            pool = load_candidates(api, persona=persona, check=check, rng=rng)
            pick = _take_pick(persona.style, pool, used, rng, persona.assets, any_live=False)
        if pick is None:
            pick = _take_pick(persona.style, pool, used, rng, persona.assets, any_live=True)
        if pick is None:
            note = note or NO_MARKET
            break
        amount = pick_amount(persona.style, cfg, cash, rng)
        if amount < MIN_BET:
            note = NO_FUNDS
            break
        ok, spent, fail = _one_trade(api, pick, amount, check, persona=persona, rng=rng)
        used.add((pick.market_id, pick.outcome))
        if ok:
            placed += 1
            cash = max(0.0, cash - spent)
            between_bets(cfg, persona.tempo, check, rng, allow_long=pick.seconds_left > 50)
            continue
        if fail:
            note = fail
            between_bets(cfg, persona.tempo, check, rng, allow_long=False)
    return placed, cash, note


def _one_trade(
    api: AceClient,
    pick: Candidate,
    amount: int,
    check: CancelCheck,
    *,
    persona: Persona,
    rng: random.Random,
) -> tuple[bool, float, str]:
    body = {
        "outcomeId": pick.outcome,
        "amount": amount,
        "isBuy": True,
        "denomination": "acepyr",
    }
    last = ""
    for attempt in range(1, TRADE_RETRIES + 1):
        check()
        if pick.seconds_left < MIN_SECONDS_LEFT:
            return False, 0.0, WINDOW_CLOSED
        quote = api.post_json(f"/api/markets/{pick.market_id}/quote", body)
        if isinstance(quote, dict) and quote.get("success") is False:
            last = error_text(quote) or "Котировка не прошла"
            if attempt < TRADE_RETRIES:
                continue
            return False, 0.0, last
        if not quote_is_valid(quote if isinstance(quote, dict) else None):
            last = "Пул не принял такой размер"
            if attempt < TRADE_RETRIES:
                body = dict(body)
                body["amount"] = max(MIN_BET, int(amount * 0.5))
                continue
            return False, 0.0, last
        trade_body = dict(body)
        trade_body["maxCost"] = quote_max_cost(float(body["amount"]), quote if isinstance(quote, dict) else None)
        between_quote_and_trade(persona.tempo, check, rng)
        traded = api.post_json(f"/api/markets/{pick.market_id}/trade", trade_body)
        if trade_ok(traded if isinstance(traded, dict) else None):
            return True, float(body["amount"]), ""
        last = error_text(traded) or "Ставка не прошла"
        if attempt < TRADE_RETRIES:
            continue
        return False, 0.0, last
    return False, 0.0, last or "Ставка не прошла"


def error_text(payload: Any) -> str:
    from .parse import error_message

    text = error_message(payload)
    lowered = text.lower()
    if "insufficient" in lowered or "balance" in lowered:
        return NO_FUNDS
    if "auth" in lowered:
        return NOT_LOGGED_IN
    return text[:180]


def maybe_link_wallet(
    api: AceClient,
    private_key: str,
    user: dict[str, Any],
    check: CancelCheck,
    *,
    persona: Persona,
    rng: random.Random,
) -> str:
    from .utils import address_from_key

    address = address_from_key(private_key)
    if already_linked(user, address):
        return "already"
    check()
    between_api(persona.tempo, check, rng)
    try:
        return link_wallet(api, private_key, user)
    except SoftError:
        return "skipped"
