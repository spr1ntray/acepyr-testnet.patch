from __future__ import annotations

from plugin.ace_bot.parse import (
    parse_balance,
    parse_me,
    quote_is_valid,
    quote_max_cost,
    trade_ok,
)


def test_parse_me_accepts_har_shape() -> None:
    user = parse_me({"user": {"id": "15355dcf-58fa-4ae4-9401-c7b6ea398e44", "username": "sprintray"}})
    assert user is not None
    assert user["username"] == "sprintray"


def test_parse_me_rejects_auth_error() -> None:
    assert parse_me({"success": False, "error": {"code": "AUTH_TOKEN_MISSING"}}) is None


def test_parse_balance() -> None:
    assert parse_balance({"success": True, "data": {"balance": "704.24952521", "tokenType": "acepyr"}}) == 704.24952521


def test_quote_max_cost_uses_total_and_slippage() -> None:
    quote = {"success": True, "data": {"isValid": True, "totalCost": 10.0}}
    assert quote_is_valid(quote)
    assert quote_max_cost(10, quote) == 10.2


def test_invalid_quote() -> None:
    quote = {"success": True, "data": {"isValid": False, "maxCost": 5, "maxShares": 1}}
    assert quote_is_valid(quote) is False


def test_trade_ok_from_har() -> None:
    payload = {
        "success": True,
        "data": {"success": True, "transactionId": "ed7a2873-3ff6-4736-9bcf-0b5ab243c22b", "impliedProbability": 0.5049},
        "predictionRecord": {"ok": True},
    }
    assert trade_ok(payload)
