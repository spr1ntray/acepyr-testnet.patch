from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from plugin.ace_bot.auth import ensure_session
from plugin.ace_bot.errors import BlockedError, SoftError
from plugin.ace_bot.utils import address_from_key

TEST_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


class FakeClient:
    def __init__(self, *, ok: bool = True, captcha: bool = False) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.bearer = ""
        self.ok = ok
        self.captcha = captcha
        self._authed = False

    def get_text(self, path: str) -> str:
        self.calls.append(("GET_TEXT", path))
        return "<html>"

    def get_json(self, path: str) -> dict[str, Any]:
        self.calls.append(("GET", path))
        if path == "/api/auth/me":
            if self._authed or self.bearer:
                return {"success": True, "data": {"user": {"id": "u1", "username": "bob"}}}
            raise BlockedError("not_logged_in", "нет сессии")
        if path.startswith("/api/consent/required"):
            return {"success": True, "data": {"satisfied": True}}
        return {}

    def post_json(self, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        self.calls.append(("POST", path, body))
        return {"success": True}

    def set_bearer(self, token: str) -> None:
        self.bearer = token
        self._authed = True

    def request_url(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        self.calls.append((method, url, json_body))
        if "grant_type=web3" in url:
            if self.captcha:
                return 403, {"error": {"code": "captcha_failed"}}
            if self.ok:
                return 200, {"access_token": "tok_wallet_aaaaaaaa"}
            return 400, {"error": "invalid_grant"}
        return 200, {}


def _login(client: FakeClient) -> dict[str, Any]:
    return ensure_session(
        client,
        account_id="acct-1",
        private_key=TEST_KEY,
        capsolver_key="CAP-TEST-KEY",
        proxy="http://u:p@10.0.0.1:8000",
        check=lambda: None,
    )


def test_wallet_login_sets_bearer() -> None:
    client = FakeClient(ok=True)
    with patch("plugin.ace_bot.auth.solve_turnstile", return_value="cf-login"):
        user = _login(client)
    assert user["username"] == "bob"
    assert client.bearer == "tok_wallet_aaaaaaaa"
    web3 = next(item for item in client.calls if item[0] == "POST" and "grant_type=web3" in str(item[1]))
    body = web3[2]
    assert body["chain"] == "ethereum"
    assert address_from_key(TEST_KEY) in body["message"]
    assert "Sign in to Acepyr" in body["message"]
    assert body["signature"].startswith("0x")
    paths = [item[1] for item in client.calls if item[0] == "POST"]
    assert "/api/auth/session/record" in paths


def test_wallet_reject_is_soft_error() -> None:
    client = FakeClient(ok=False)
    with patch("plugin.ace_bot.auth.solve_turnstile", return_value="cf"):
        with pytest.raises(SoftError) as exc:
            _login(client)
    assert exc.value.code == "auth_wallet"


def test_captcha_reject_on_web3() -> None:
    client = FakeClient(captcha=True)
    with patch("plugin.ace_bot.auth.solve_turnstile", return_value="cf"):
        with pytest.raises(SoftError) as exc:
            _login(client)
    assert exc.value.code == "captcha"
