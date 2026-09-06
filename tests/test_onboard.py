from __future__ import annotations

from typing import Any
from uuid import uuid4

from plugin.ace_bot.onboard import NameBank, complete_profile, mint_username, stable_dob, username_candidates


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.claimed: str | None = None

    def get_json(self, path: str) -> dict[str, Any]:
        self.calls.append(("GET", path))
        if path.startswith("/api/consent/required"):
            return {
                "success": True,
                "data": {
                    "satisfied": False,
                    "outstanding": [
                        {"consentType": "terms_of_service", "textHash": "abc"}
                    ],
                },
            }
        if path.startswith("/api/auth/check-username"):
            if "aceffff" in path:
                return {"success": True, "data": {"available": False}}
            return {"success": True, "data": {"available": True}}
        return {}

    def post_json(self, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        self.calls.append(("POST", path, body))
        return {"success": True}

    def put_json(
        self,
        path: str,
        body: dict[str, Any] | None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(("PUT", path, body, extra_headers))
        self.claimed = str((body or {}).get("username") or "")
        return {"success": True}


def test_mint_username_is_unique_per_account() -> None:
    left = mint_username("acct-1")
    right = mint_username("acct-2")
    assert left != right
    assert mint_username("acct-1") == left
    assert left[0].isalpha()
    assert 3 <= len(left) <= 50


def test_username_candidates_do_not_repeat() -> None:
    names = username_candidates("acct-unique")
    assert len(names) == len(set(name.lower() for name in names))
    spread = {mint_username(str(uuid4())) for _ in range(80)}
    assert len(spread) == 80


def test_name_bank_rejects_duplicates() -> None:
    bank = NameBank()
    assert bank.claim("AlphaOne") is True
    assert bank.claim("alphaone") is False
    bank.remember("BetaTwo")
    assert bank.claim("BetaTwo") is False


def test_stable_dob_is_adult() -> None:
    dob = stable_dob("acct-1")
    year = int(dob[:4])
    assert 1984 <= year <= 2001
    assert dob == stable_dob("acct-1")


def test_complete_profile_puts_username() -> None:
    client = FakeClient()
    name = complete_profile(
        client,
        account_id="acct-1",
        check=lambda: None,
        existing={"needsUsername": True},
    )
    assert name == mint_username("acct-1")
    grants = [c for c in client.calls if c[0] == "POST" and c[1] == "/api/consent/grant"]
    assert grants
    assert grants[0][2]["consent_type"] == "terms_of_service"
    puts = [c for c in client.calls if c[0] == "PUT"]
    assert puts
    assert puts[0][2]["username"] == name
    assert "dateOfBirth" in puts[0][2]
    assert puts[0][3]["Idempotency-Key"]


def test_complete_profile_applies_parent_code() -> None:
    client = FakeClient()
    protected: list[str] = []

    def protect(value: str) -> str:
        protected.append(value)
        return value

    name = complete_profile(
        client,
        account_id="acct-2",
        check=lambda: None,
        referral_code="ParentNick",
        existing={"needsUsername": True},
        protect=protect,
    )
    assert name == mint_username("acct-2")
    complete = [c for c in client.calls if c[0] == "POST" and c[1] == "/api/auth/email-otp/complete"]
    assert complete
    assert complete[0][2]["referralCode"] == "ParentNick"
    assert complete[0][2]["username"] == name
    assert protected == ["ParentNick"]
