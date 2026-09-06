from __future__ import annotations

from .config import STRATEGY_LABELS


def ru_count(n: int, one: str, few: str, many: str) -> str:
    value = abs(int(n))
    mod10, mod100 = value % 10, value % 100
    if mod10 == 1 and mod100 != 11:
        word = one
    elif 2 <= mod10 <= 4 and not (12 <= mod100 <= 14):
        word = few
    else:
        word = many
    return f"{value} {word}"


def bets_phrase(n: int) -> str:
    return ru_count(n, "ставка", "ставки", "ставок")


def style_label(style: str) -> str:
    return STRATEGY_LABELS.get(style, style)


NO_FUNDS = "Нет тестовых денег на ставку"
NOT_LOGGED_IN = "Не удалось войти в Acepyr"
NEED_USERNAME = "Acepyr просит задать ник. Сделай это один раз в профиле и повтори запуск"
NO_MARKET = "Стиль не нашёл подходящий рынок в этом окне"
WINDOW_CLOSED = "Пятиминутка уже закрывается, ставку пропустили"


def is_no_funds(note: str) -> bool:
    text = (note or "").lower()
    return any(token in text for token in ("тестовых денег", "наличных нет", "нет тестовых"))


def farm_status(placed: int, note: str = "") -> str:
    if placed > 0:
        return "succeeded"
    if is_no_funds(note) or note == NOT_LOGGED_IN or note == NEED_USERNAME:
        return "blocked"
    return "partial"


def farm_result_message(style: str, placed: int, note: str = "") -> str:
    if placed <= 0:
        return note or "Сессия живая, ставок не вышло"
    text = f"{bets_phrase(placed)}, стиль «{style_label(style)}»"
    if note and not is_no_funds(note):
        return f"{text}. {note}"
    return text
