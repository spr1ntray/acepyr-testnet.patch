from __future__ import annotations

from dataclasses import dataclass

SITE = "https://www.acepyr.com"
ORIGIN = SITE
TURNSTILE_SITEKEY = "0x4AAAAAAD6N7R5hpRAwXO4o"
TURNSTILE_PAGE = f"{SITE}/live"
WALLET_AUTH_STATEMENT = (
    "Sign in to Acepyr. This request will not trigger a blockchain transaction or cost any gas."
)
SIWE_CHAIN_ID = 1
SUPABASE_URL = "https://cwwostwvnroucwjnmpak.supabase.co"
SUPABASE_ANON = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN3d29zdHd2bnJvdWN3am5tcGFrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE2MDAwNzQsImV4cCI6MjA5NzE3NjA3NH0."
    "vYRzASo9K642a_7T1lm1025mQWp8meBVlbQHP4j74vI"
)
BETS_MAX = 20
MIN_BET = 1
SLIPPAGE = 1.02
MIN_SECONDS_LEFT = 25
MARKET_WAIT_SECONDS = 300
PAGE_TIMEOUT_MS = 45000
FETCH_TIMEOUT_MS = 30000
TRADE_RETRIES = 2

STRATEGY_LABELS = {
    "confident": "уверенный",
    "cautious": "осторожный",
    "mixed": "смешанный",
    "momentum": "по движению",
    "crowd": "за толпой",
    "crazy": "рисковый",
}

# hash % 100 buckets — stable per account
STRATEGY_RANGES = (
    ("confident", 0, 28),
    ("cautious", 28, 50),
    ("mixed", 50, 68),
    ("momentum", 68, 82),
    ("crowd", 82, 94),
    ("crazy", 94, 100),
)

SPICE_CHANCE = {
    "confident": 0.10,
    "cautious": 0.07,
    "mixed": 0.12,
    "momentum": 0.10,
    "crowd": 0.10,
    "crazy": 0.0,
}

EXTRA_PATHS = ("/news", "/leaderboard", "/faucet", "/live-plays", "/home")
ASSET_ORDER = ("BTC", "ETH", "SOL", "BNB", "XRP", "HYPE")


@dataclass(frozen=True)
class RunConfig:
    bets_from: int = 2
    bets_to: int = 4
    bet_from: int = 10
    bet_to: int = 100
    pause_from_ms: int = 800
    pause_to_ms: int = 2400
    request_timeout: int = 45
