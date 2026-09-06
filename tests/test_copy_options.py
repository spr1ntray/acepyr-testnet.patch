from __future__ import annotations

import pytest

from plugin.ace_bot.copy import farm_result_message, farm_status
from plugin.ace_bot.options import farm_config


def test_farm_status_no_cash_is_blocked() -> None:
    assert farm_status(0, "Нет тестовых денег на ставку") == "blocked"
    assert farm_status(2, "") == "succeeded"
    assert farm_status(0, "Стиль не нашёл подходящий рынок в этом окне") == "partial"


def test_farm_result_message_russian() -> None:
    text = farm_result_message("confident", 3)
    assert "3 ставки" in text
    assert "уверенный" in text


def test_farm_config_rejects_inverted_range() -> None:
    with pytest.raises(ValueError):
        farm_config({"bets_from": 5, "bets_to": 2})


def test_farm_config_defaults() -> None:
    cfg = farm_config({})
    assert cfg.bets_from == 2
    assert cfg.bet_to == 100
