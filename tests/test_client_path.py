from __future__ import annotations

import pytest

from plugin.ace_bot.errors import SoftError
from plugin.ace_bot.http import assert_api_path


def test_api_path_allowlist() -> None:
    assert assert_api_path("/api/auth/me") == "/api/auth/me"
    with pytest.raises(SoftError):
        assert_api_path("https://evil.test/api/auth/me")
    with pytest.raises(SoftError):
        assert_api_path("/api/../secret")
    with pytest.raises(SoftError):
        assert_api_path("/live")


def test_fetch_headers_match_chrome() -> None:
    from plugin.ace_bot.http import AceClient
    from plugin.ace_bot.identity import pick_identity

    client = AceClient(pick_identity("hdr-check"), None)
    try:
        headers = client._headers()
        assert headers["Accept"] == "*/*"
        assert "Cache-Control" not in headers
        assert "Pragma" not in headers
        assert headers["Priority"] == "u=1, i"
        assert "Origin" not in headers
        posted = client._headers(origin=True)
        assert posted["Origin"] == "https://www.acepyr.com"
        page = client._headers(navigate=True)
        assert "text/html" in page["Accept"]
        assert page["Sec-Fetch-Mode"] == "navigate"
        assert page["Sec-Fetch-Dest"] == "document"
        assert "10_15_7" in client.identity.user_agent or "Windows NT 10.0" in client.identity.user_agent
        assert f"Chrome/{client.identity.chrome_major}.0.0.0" in client.identity.user_agent
    finally:
        client.close()
