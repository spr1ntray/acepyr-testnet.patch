from __future__ import annotations

from uuid import uuid4

from plugin.ace_bot.identity import identity_from_adspower, load_bank, pick_identity
from plugin.adspower import identity_for


def test_bank_has_200_profiles() -> None:
    bank = load_bank()
    assert len(bank) == 200
    assert {row["user_agent"] for row in bank if row.get("user_agent")}


def test_same_account_keeps_identity() -> None:
    account_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    left = pick_identity(account_id)
    right = pick_identity(account_id)
    assert left.user_agent == right.user_agent
    assert left.device_id == right.device_id
    assert left.source == "bank"


def test_accounts_spread_across_bank() -> None:
    indexes = {pick_identity(str(uuid4())).index for _ in range(80)}
    assert len(indexes) > 20


def test_adspower_overlay_keeps_device_and_fills_ua() -> None:
    base = pick_identity("overlay-account")
    overlay = identity_from_adspower(
        {
            "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            "fingerprint_config": {
                "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
                "language": ["de-DE", "de", "en"],
                "timezone": "Europe/Berlin",
                "screen_resolution": "1440x900",
                "hardware_concurrency": 10,
            },
        },
        base,
    )
    assert overlay.source == "adspower"
    assert overlay.platform == "macOS"
    assert overlay.timezone == "Europe/Berlin"
    assert overlay.device_id == base.device_id
    assert "Chrome/136" in overlay.user_agent
    assert overlay.impersonate == "chrome136"
    assert "Intel Mac OS X 10_15_7" in overlay.user_agent
    assert "Chrome/136.0.0.0" in overlay.user_agent


class _Account:
    def __init__(self, account_id: str) -> None:
        self.id = account_id

    def secret(self, name: str) -> str:
        raise KeyError(name)


class _Ctx:
    class settings:
        @staticmethod
        def secret(name: str) -> str:
            raise KeyError(name)


def test_identity_for_falls_back_to_bank() -> None:
    ident = identity_for(_Ctx(), _Account("no-ads-account"))
    assert ident.source == "bank"
    assert ident.user_agent
    assert ident.sec_ch_ua


def test_bank_uses_frozen_chrome_ua() -> None:
    from plugin.ace_bot.identity import load_bank, pick_identity

    for row in load_bank():
        major = int(row["chrome_major"])
        ua = row["user_agent"]
        assert f"Chrome/{major}.0.0.0" in ua
        if row["platform"] == "macOS":
            assert "Intel Mac OS X 10_15_7" in ua
        else:
            assert "Windows NT 10.0; Win64; x64" in ua
        assert row["impersonate"] in {"chrome120", "chrome124", "chrome131", "chrome136"}
        assert f'v="{major}"' in row["sec_ch_ua"]
    ident = pick_identity("frozen-check")
    assert ident.user_agent == ident.user_agent
    assert "10_15_7" in ident.user_agent or "Windows NT 10.0" in ident.user_agent
    assert f"Chrome/{ident.chrome_major}.0.0.0" in ident.user_agent
