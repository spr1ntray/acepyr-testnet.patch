from __future__ import annotations

from typing import Any
from urllib.parse import quote

from eth_account import Account
from eth_account.messages import encode_defunct

from .errors import SoftError
from .parse import unwrap
from .utils import normalize_private_key


def challenge_message(payload: Any) -> str:
    body = unwrap(payload)
    if isinstance(body, dict):
        text = str(body.get("message") or "").strip()
        if text:
            return text
    if isinstance(payload, dict):
        text = str(payload.get("message") or "").strip()
        if text:
            return text
    return ""


def siwe_message(
    address: str,
    *,
    issued_at: str,
    uri: str,
    chain_id: int,
    statement: str,
    domain: str = "www.acepyr.com",
) -> str:
    return (
        f"{domain} wants you to sign in with your Ethereum account:\n"
        f"{address}\n"
        f"\n"
        f"{statement}\n"
        f"\n"
        f"URI: {uri}\n"
        f"Version: 1\n"
        f"Chain ID: {chain_id}\n"
        f"Issued At: {issued_at}"
    )


def sign_message(private_key: str, message: str) -> str:
    key = normalize_private_key(private_key)
    signed = Account.sign_message(encode_defunct(text=message), private_key=key)
    signature = signed.signature.hex()
    if not signature.startswith("0x"):
        signature = "0x" + signature
    return signature


def challenge_path(address: str) -> str:
    return f"/api/user/link-wallet/challenge?chain=ethereum&address={quote(address)}"


def already_linked(user: dict[str, Any] | None, address: str) -> bool:
    if not isinstance(user, dict):
        return False
    current = str(user.get("walletAddress") or user.get("walletCredentialAddress") or "").lower()
    return current == address.lower()


def link_wallet(api: Any, private_key: str, user: dict[str, Any] | None) -> str:
    """Returns 'linked', 'already', or raises SoftError. `api` is AceClient."""
    from .utils import address_from_key

    address = address_from_key(private_key)
    if already_linked(user, address):
        return "already"
    raw = api.get_json(challenge_path(address))
    message = challenge_message(raw)
    if not message:
        raise SoftError("wallet_challenge", "Acepyr не выдал сообщение для привязки кошелька")
    signature = sign_message(private_key, message)
    verify = api.post_json(
        "/api/user/link-wallet/verify",
        {"address": address, "message": message, "signature": signature},
    )
    if isinstance(verify, dict) and verify.get("success") is False:
        raise SoftError("wallet_verify", "Не удалось привязать кошелёк")
    return "linked"
