from __future__ import annotations

from unittest.mock import patch

import pytest

from plugin.ace_bot.capsolver import capsolver_proxy, solve_turnstile
from plugin.ace_bot.errors import SoftError


def test_capsolver_proxy_packs_url() -> None:
    assert capsolver_proxy("http://user:p%40ss@10.0.0.2:8000") == "10.0.0.2:8000:user:p@ss"
    assert capsolver_proxy("http://user:pass@10.0.0.2:8000") == "10.0.0.2:8000:user:pass"
    assert capsolver_proxy("10.0.0.2:8000:user:pass") == "10.0.0.2:8000:user:pass"


def test_solve_turnstile_requires_key() -> None:
    with pytest.raises(SoftError) as exc:
        solve_turnstile("ab", site_key="0x4", page_url="https://www.acepyr.com/live")
    assert exc.value.code == "capsolver_missing"


def test_solve_turnstile_returns_token() -> None:
    responses = [
        {"taskId": "t1", "errorId": 0},
        {"status": "processing", "errorId": 0},
        {"status": "ready", "errorId": 0, "solution": {"token": "cf-turnstile-ok"}},
    ]

    def fake_post(url, json=None, timeout=60):
        class Resp:
            status_code = 200

            def json(self):
                return responses.pop(0)

        return Resp()

    with (
        patch("plugin.ace_bot.capsolver.requests.post", side_effect=fake_post),
        patch("plugin.ace_bot.capsolver.time.sleep"),
    ):
        token = solve_turnstile(
            "CAP-TEST-KEY",
            site_key="0x4AAAAAAD6N7R5hpRAwXO4o",
            page_url="https://www.acepyr.com/live",
            action="login",
        )
    assert token == "cf-turnstile-ok"
    assert responses == []
