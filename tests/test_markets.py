from __future__ import annotations

from plugin.ace_bot.markets import (
    candidates_from_market,
    crowd_side_from_plays,
    parse_five_min,
    parse_prices,
    seconds_left,
)


def test_parse_five_min_active_row() -> None:
    payload = {
        "success": True,
        "serverNow": "2026-09-01T08:36:00.000Z",
        "data": [
            {
                "symbol": "BTC",
                "active": {
                    "marketId": "fa90aa83-790d-45a7-bb1d-a785ae17d74b",
                    "symbol": "BTC",
                    "title": "BTC Up or Down (08:35–08:40 UTC)",
                    "slug": "btc-up-or-down-5min-202609010835",
                    "status": "active",
                    "windowEnd": "2026-09-01T08:40:00.000Z",
                    "upProbability": 0.42,
                    "priceToBeat": 78000,
                    "currentPrice": 77950,
                }
            }
        ],
    }
    rows = parse_five_min(payload)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTC"
    assert 200 < rows[0]["seconds_left"] < 260


def test_candidates_use_implied_probability() -> None:
    market = {
        "market_id": "m1",
        "slug": "btc",
        "symbol": "BTC",
        "title": "BTC",
        "status": "active",
        "seconds_left": 90,
        "price_to_beat": 100.0,
        "current_price": 99.0,
    }
    prices = parse_prices(
        {
            "success": True,
            "data": {
                "up": {"impliedProbability": 0.21, "price": 0.21},
                "down": {"impliedProbability": 0.79, "price": 0.79},
            },
        }
    )
    found = candidates_from_market(market, prices, crowd_side="down")
    assert {item.outcome: item.probability for item in found} == {"up": 0.21, "down": 0.79}
    assert found[0].crowd_side == "down"


def test_seconds_left_zero_on_bad_date() -> None:
    assert seconds_left("not-a-date", 1.0) == 0.0


def test_crowd_side_weights_size() -> None:
    plays = [
        {"marketId": "m1", "action": "bought", "optionLabel": "Up", "value": "1"},
        {"marketId": "m1", "action": "bought", "optionLabel": "Down", "value": "50"},
        {"marketId": "other", "action": "bought", "optionLabel": "Up", "value": "999"},
    ]
    assert crowd_side_from_plays(plays, "m1") == "down"
