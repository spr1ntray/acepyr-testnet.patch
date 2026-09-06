from __future__ import annotations

from eth_account import Account
from eth_account.messages import encode_defunct

from plugin.ace_bot.config import TURNSTILE_PAGE, WALLET_AUTH_STATEMENT
from plugin.ace_bot.wallet import already_linked, challenge_message, challenge_path, sign_message, siwe_message


def test_challenge_message_unwrap() -> None:
    assert challenge_message({"success": True, "data": {"message": "Sign this"}}) == "Sign this"
    assert challenge_message({"message": "Hello"}) == "Hello"


def test_sign_message_roundtrip() -> None:
    key = "0x" + ("11" * 32)
    message = "link acepyr"
    signature = sign_message(key, message)
    recovered = Account.recover_message(encode_defunct(text=message), signature=signature)
    assert recovered.lower() == Account.from_key(key).address.lower()


def test_already_linked() -> None:
    key = "0x" + ("11" * 32)
    address = Account.from_key(key).address
    assert already_linked({"walletAddress": address}, address) is True
    assert already_linked({"walletAddress": "0x" + "ab" * 20}, address) is False


def test_challenge_path_encodes_address() -> None:
    path = challenge_path("0xABC")
    assert path.startswith("/api/user/link-wallet/challenge?")
    assert "ethereum" in path


def test_siwe_message_matches_site() -> None:
    text = siwe_message(
        "0x1234",
        issued_at="2026-09-05T12:00:00.000Z",
        uri=TURNSTILE_PAGE,
        chain_id=1,
        statement=WALLET_AUTH_STATEMENT,
    )
    assert text.startswith("www.acepyr.com wants you to sign in with your Ethereum account:")
    assert "\n0x1234\n\nSign in to Acepyr." in text
    assert "URI: https://www.acepyr.com/live" in text
    assert "Chain ID: 1" in text
    assert "Issued At: 2026-09-05T12:00:00.000Z" in text
