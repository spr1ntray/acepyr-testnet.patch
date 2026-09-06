from __future__ import annotations

from plugin.ace_bot.identity import pick_identity
from plugin.adspower import fetch_profile, identity_for


def test_fetch_profile_ignores_short_id() -> None:
    assert fetch_profile("") is None
    assert fetch_profile("abc") is None


def test_identity_for_without_ads_secret() -> None:
    class Account:
        id = "acct-1"

        def secret(self, name: str) -> str:
            raise KeyError(name)

    class Ctx:
        class settings:
            @staticmethod
            def secret(name: str) -> str:
                raise KeyError(name)

    ident = identity_for(Ctx(), Account())
    assert ident.source == "bank"
    assert ident.user_agent == pick_identity("acct-1").user_agent
