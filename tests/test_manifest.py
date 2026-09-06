from __future__ import annotations

import json
from pathlib import Path


def _manifest() -> dict:
    path = Path(__file__).resolve().parents[1] / "acepyr-testnet" / "hub.plugin.json"
    return json.loads(path.read_text())


def test_card_description_fits_hub() -> None:
    manifest = _manifest()
    short = manifest["description"]
    full = manifest["presentation"]["description"]
    assert 1 <= len(short) <= 500
    assert 80 <= len(full) <= 400
    assert "тест" in full.lower()
    assert "став" in full.lower()
    assert "прокси" in full.lower()
    assert "почт" not in full.lower()


def test_contract_catalog_and_risk() -> None:
    manifest = _manifest()
    assert manifest["version"] == "1.2.6"
    assert manifest["contract_version"] == "SH-SOFTWARE-0.6/5"
    assert manifest["catalog"]["sections"] == ["testnet"]
    assert manifest["permissions"]["financial_risk"] == "none"
    assert manifest["permissions"]["browser"] is False
    assert manifest["permissions"]["local_services"] == []
    risks = {action["risk"] for action in manifest["actions"]}
    assert "mainnet_write" not in risks
    assert "testnet_write" not in risks
    farm = next(action for action in manifest["actions"] if action["id"] == "farm")
    inspect = next(action for action in manifest["actions"] if action["id"] == "inspect")
    assert farm["risk"] == "external_write"
    assert inspect["risk"] == "external_write"
    assert "adspower_profile" not in farm["resources"]["account"]
    assert "capsolver" not in farm.get("options", {}).get("properties", {})
    assert "capsolver" not in inspect.get("options", {}).get("properties", {})


def test_farm_copy_is_plain_russian() -> None:
    farm = next(action for action in _manifest()["actions"] if action["id"] == "farm")
    assert farm["name"] == "Прогнать аккаунты"
    conc = farm["options"]["properties"]["account_concurrency"]["description"]
    assert "5–10" in conc or "5-10" in conc


def test_farm_slider_grids_fit_hub_limit() -> None:
    farm = next(action for action in _manifest()["actions"] if action["id"] == "farm")
    props = farm["options"]["properties"]
    assert props["account_concurrency"]["maximum"] == 20
    for key in ("bet_from", "bet_to", "bets_from", "bets_to", "pause_from_ms", "pause_to_ms"):
        field = props[key]
        step = field["multipleOf"]
        steps = (field["maximum"] - field["minimum"]) / step
        assert 1 <= steps <= 1000
        assert field["minimum"] % step == 0
        assert field["maximum"] % step == 0
        assert field["default"] % step == 0


def test_inspect_has_account_table() -> None:
    inspect = next(action for action in _manifest()["actions"] if action["id"] == "inspect")
    assert inspect["output"]["primary_kind"] == "account_snapshot"
    columns = {col["key"] for col in inspect["output"]["columns"]}
    assert {"strategy", "balance", "session", "wallet_linked"} <= columns


_SECRET_RESOURCE = {
    "evm_private_key": ("account", "private_key"),
    "proxy": ("account", "proxy"),
    "email": ("account", "email"),
    "email_password": ("account", "email_password"),
    "capsolver_api_key": ("settings", "capsolver"),
    "adspower_api_key": ("settings", "adspower_api"),
    "adspower_profile": ("account", "adspower_profile"),
}

_RESERVED_OPTIONS = {
    "capsolver",
    "capsolver_key",
    "capsolver_api_key",
    "cap_solver_api_key",
    "captcha_key",
    "captcha_api_key",
    "adspower_api",
    "adspower_key",
    "adspower_api_key",
}


def test_secret_union_matches_actions() -> None:
    manifest = _manifest()
    top = set(manifest["permissions"]["secrets"])
    union: set[str] = set()
    for action in manifest["actions"]:
        secrets = set(action["permissions"]["secrets"])
        assert secrets <= top
        union |= secrets
    assert union == top
    assert {
        "evm_private_key",
        "proxy",
        "capsolver_api_key",
    } == top
    assert "email" not in top
    assert "email_password" not in top


def test_resources_match_secrets() -> None:
    for action in _manifest()["actions"]:
        secrets = set(action["permissions"]["secrets"])
        account = set(action["resources"]["account"])
        settings = set(action["resources"]["settings"])
        for secret in secrets:
            group, name = _SECRET_RESOURCE[secret]
            bucket = account if group == "account" else settings
            assert name in bucket
        assert "capsolver" in settings
        props = action.get("options", {}).get("properties", {})
        assert _RESERVED_OPTIONS.isdisjoint(props)


def test_farm_referral_contract() -> None:
    farm = next(action for action in _manifest()["actions"] if action["id"] == "farm")
    referral = farm["referral"]
    assert referral["mode"] == "project_runtime"
    assert referral["parent_required"] is False
    assert referral["parent_access"] == "shared_read"
    assert referral["permissions"]["secrets"] == []
    assert referral["resources"]["account"] == []
    assert "referral_code" not in farm["options"]["properties"]
    assert "referrer_code" not in farm["options"]["properties"]
    columns = {col["key"] for col in farm["output"]["columns"]}
    assert "referred" in columns


def test_network_includes_login_hosts() -> None:
    hosts = set(_manifest()["permissions"]["network"])
    assert "www.acepyr.com" in hosts
    assert "api.capsolver.com" in hosts
    assert "cwwostwvnroucwjnmpak.supabase.co" in hosts
    assert "imap.firstmail.ltd" not in hosts


def test_assets_exist() -> None:
    root = Path(__file__).resolve().parents[1] / "acepyr-testnet"
    manifest = _manifest()
    icon = root / manifest["presentation"]["assets"]["icon"]
    image = root / manifest["presentation"]["assets"]["image"]
    assert icon.is_file() and icon.stat().st_size > 1000
    assert image.is_file() and image.stat().st_size > 1000
    assert icon.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
