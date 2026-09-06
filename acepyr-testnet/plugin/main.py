from __future__ import annotations

import random
import threading
from typing import Any

from plugin.ace_bot.auth import ensure_session
from plugin.ace_bot.copy import farm_result_message, farm_status, style_label
from plugin.ace_bot.errors import BlockedError, SoftError
from plugin.ace_bot.flow import maybe_link_wallet, place_bets, snapshot, visit_faucet, warmup
from plugin.ace_bot.http import AceClient
from plugin.ace_bot.onboard import NameBank
from plugin.ace_bot.options import farm_config
from plugin.ace_bot.pace import between_bets, start_delay
from plugin.ace_bot.strategy import persona_for
from plugin.ace_bot.utils import address_from_key, scrub_secrets
from plugin.adspower import identity_for
from soft_hub.sdk import CancelledError, HubAccount, HubContext


def run(context: HubContext) -> dict[str, Any]:
    if context.action_id == "inspect":
        return _run_inspect(context)
    if context.action_id == "farm":
        return _run_farm(context)
    raise ValueError("unsupported_action")


def _run_inspect(context: HubContext) -> dict[str, Any]:
    counters = {
        "total": len(context.accounts),
        "succeeded": 0,
        "failed": 0,
        "blocked": 0,
        "cancelled": 0,
    }
    lock = threading.Lock()
    names = NameBank()

    def worker(account: HubAccount) -> str:
        try:
            status = _inspect_one(context, account, names)
        except CancelledError:
            with lock:
                counters["cancelled"] += 1
            raise
        except Exception:
            _fail_unknown(context, account, kind="account_snapshot")
            with lock:
                counters["failed"] += 1
            return "failed"
        with lock:
            counters[status] = counters.get(status, 0) + 1
        return status

    context.map_accounts(worker)
    return counters


def _run_farm(context: HubContext) -> dict[str, Any]:
    cfg = farm_config(context.options)
    counters = {
        "total": len(context.accounts),
        "succeeded": 0,
        "partial": 0,
        "failed": 0,
        "blocked": 0,
        "cancelled": 0,
        "bets": 0,
    }
    lock = threading.Lock()
    names: dict[str, str] = {}
    names_lock = threading.Lock()
    bank = NameBank()
    levels = _referral_levels(context)

    def worker(account: HubAccount) -> str:
        parent_code = _parent_code(context, account, names, names_lock)
        try:
            status, placed, username = _farm_one(context, account, cfg, parent_code, bank)
        except CancelledError:
            with lock:
                counters["cancelled"] += 1
            raise
        except Exception:
            _fail_unknown(context, account, kind="farm_summary")
            with lock:
                counters["failed"] += 1
            return "failed"
        if username:
            _protect(context, username)
            with names_lock:
                names[account.id] = username
        with lock:
            counters[status] = counters.get(status, 0) + 1
            counters["bets"] += placed
        return status

    try:
        for index, level in enumerate(levels):
            context.check_cancelled()
            context.log(
                f"Реферальная цепь, уровень {index}: {len(level)} аккаунтов",
                data={"level": index, "accounts": len(level)},
            )
            _map_accounts(context, worker, level)
    finally:
        with names_lock:
            names.clear()
    return counters


def _inspect_one(context: HubContext, account: HubAccount, names: NameBank) -> str:
    persona = persona_for(account.id)
    rng = random.Random()
    context.account_state(
        account.id,
        status="running",
        stage="preflight",
        progress=0.08,
        message="Собираем отпечаток запроса",
    )
    context.check_cancelled()
    try:
        private_key = account.secret("evm_private_key")
        proxy = account.secret("proxy")
        capsolver_key = str(context.settings.secret("capsolver") or "").strip()
        address_from_key(private_key)
    except (KeyError, ValueError):
        return _blocked(context, account, "Не заполнены ключ, прокси или Capsolver", kind="account_snapshot")
    if len(capsolver_key) < 4:
        return _blocked(context, account, "Не заполнены ключ, прокси или Capsolver", kind="account_snapshot")
    identity = identity_for(context, account)
    client = None
    try:
        start_delay(persona.style, context.check_cancelled, rng, tempo=persona.tempo)
        client = AceClient(identity, proxy)
        context.account_state(
            account.id,
            status="running",
            stage="auth_check",
            progress=0.45,
            message="Входим кошельком",
        )
        ensure_session(
            client,
            account_id=account.id,
            private_key=private_key,
            capsolver_key=capsolver_key,
            proxy=proxy,
            check=context.check_cancelled,
            protect=getattr(context, "protect_secret", None),
            names=names,
        )
        snap = snapshot(client)
    except BlockedError as exc:
        return _blocked(context, account, str(exc), kind="account_snapshot")
    except SoftError as exc:
        return _failed(context, account, str(exc), kind="account_snapshot")
    finally:
        if client is not None:
            client.close()
    context.result(
        f"{account.label}: кабинет прочитан",
        kind="account_snapshot",
        status="succeeded",
        account_id=account.id,
        data={
            "username": snap["username"],
            "strategy": style_label(persona.style),
            "balance": _dec(snap["balance"]),
            "bets": int(snap["bets"]),
            "wallet_linked": bool(snap["wallet_linked"]),
            "session": True,
        },
    )
    context.account_state(
        account.id,
        status="succeeded",
        stage="completed",
        progress=1.0,
        message=f"Стиль «{style_label(persona.style)}», баланс {snap['balance']:.2f}",
    )
    return "succeeded"


def _farm_one(
    context: HubContext, account: HubAccount, cfg, parent_code: str, bank: NameBank
) -> tuple[str, int, str]:
    persona = persona_for(account.id)
    rng = random.Random()
    context.account_state(
        account.id,
        status="running",
        stage="preflight",
        progress=0.06,
        message="Проверяем ключ и прокси",
    )
    context.check_cancelled()
    try:
        private_key = account.secret("evm_private_key")
        proxy = account.secret("proxy")
        capsolver_key = str(context.settings.secret("capsolver") or "").strip()
        address_from_key(private_key)
    except (KeyError, ValueError):
        return (
            _blocked(context, account, "Не заполнены ключ, прокси или Capsolver", kind="farm_summary"),
            0,
            "",
        )
    if len(capsolver_key) < 4:
        return (
            _blocked(context, account, "Не заполнены ключ, прокси или Capsolver", kind="farm_summary"),
            0,
            "",
        )
    identity = identity_for(context, account)
    start_delay(persona.style, context.check_cancelled, rng, tempo=persona.tempo)
    placed = 0
    client = None
    snap: dict[str, Any] = {}
    cash = 0.0
    note = ""
    try:
        client = AceClient(identity, proxy)
        context.account_state(
            account.id,
            status="running",
            stage="auth_check",
            progress=0.22,
            message="Входим кошельком",
        )
        warmup(client, persona, context.check_cancelled, rng)
        ensure_session(
            client,
            account_id=account.id,
            private_key=private_key,
            capsolver_key=capsolver_key,
            proxy=proxy,
            check=context.check_cancelled,
            protect=getattr(context, "protect_secret", None),
            referral_code=parent_code,
            names=bank,
        )
        snap = snapshot(client)
        context.account_state(
            account.id,
            status="running",
            stage="faucet",
            progress=0.40,
            message="Смотрим кран",
        )
        visit_faucet(client, context.check_cancelled, rng, persona)
        context.account_state(
            account.id,
            status="running",
            stage="wallet",
            progress=0.52,
            message="Сверяем кошелёк",
        )
        maybe_link_wallet(
            client,
            private_key,
            snap["user"],
            context.check_cancelled,
            persona=persona,
            rng=rng,
        )
        snap = snapshot(client)
        if snap["balance"] < 1:
            return (
                _blocked(
                    context,
                    account,
                    "Нет тестовых денег на ставку",
                    kind="farm_summary",
                    extra={
                        "username": snap["username"],
                        "strategy": style_label(persona.style),
                        "bets": 0,
                        "balance": _dec(snap["balance"]),
                        "wallet_linked": bool(snap["wallet_linked"]),
                        "referred": bool(parent_code),
                    },
                ),
                0,
                str(snap.get("username") or ""),
            )
        context.account_state(
            account.id,
            status="running",
            stage="automation",
            progress=0.68,
            message=f"Ставим в стиле «{style_label(persona.style)}»",
        )
        placed, cash, note = place_bets(
            client,
            persona=persona,
            cfg=cfg,
            balance=snap["balance"],
            check=context.check_cancelled,
            rng=rng,
        )
        between_bets(cfg, persona.tempo, context.check_cancelled, rng, allow_long=False)
        try:
            snap = snapshot(client)
            cash = snap["balance"]
        except SoftError:
            snap["balance"] = cash
    except BlockedError as exc:
        return _blocked(context, account, str(exc), kind="farm_summary"), 0, ""
    except SoftError as exc:
        return _failed(context, account, str(exc), kind="farm_summary"), placed, str(snap.get("username") or "")
    finally:
        if client is not None:
            client.close()
    status = farm_status(placed, note)
    message = farm_result_message(persona.style, placed, note)
    result_status = status if status in {"succeeded", "partial", "failed", "blocked", "skipped"} else "failed"
    username = str(snap.get("username") or "")
    context.result(
        f"{account.label}: {message}",
        kind="farm_summary",
        status=result_status,
        account_id=account.id,
        data={
            "username": username,
            "strategy": style_label(persona.style),
            "bets": placed,
            "balance": _dec(float(cash)),
            "wallet_linked": bool(snap.get("wallet_linked")),
            "referred": bool(parent_code),
        },
    )
    kwargs: dict[str, Any] = {
        "status": result_status,
        "stage": "completed" if result_status in {"succeeded", "partial"} else result_status,
        "message": message,
    }
    if result_status in {"succeeded", "partial"}:
        kwargs["progress"] = 1.0
        kwargs["stage"] = "completed"
    context.account_state(account.id, **kwargs)
    return result_status, placed, username


def _referral_levels(context: HubContext) -> tuple[tuple[HubAccount, ...], ...]:
    levels = getattr(context, "referral_levels", None)
    if levels is None:
        return (tuple(context.accounts),)
    try:
        materialised = tuple(tuple(level) for level in levels)
    except Exception:
        return (tuple(context.accounts),)
    return materialised or (tuple(context.accounts),)


def _map_accounts(context: HubContext, worker: Any, accounts: tuple[HubAccount, ...] | list[HubAccount]) -> None:
    selected = tuple(accounts)
    if not selected:
        return
    mapper = getattr(context, "map_accounts", None)
    if callable(mapper):
        try:
            mapper(worker, accounts=selected)
            return
        except TypeError:
            pass
    for account in selected:
        context.check_cancelled()
        worker(account)


def _parent_for(context: HubContext, child: HubAccount) -> HubAccount | None:
    referrals = getattr(context, "referrals", None)
    if referrals is None:
        return None
    getter = getattr(referrals, "parent_for", None)
    if not callable(getter):
        return None
    try:
        return getter(child.id)
    except KeyError:
        return None


def _protect(context: HubContext, value: str) -> str:
    token = (value or "").strip()
    if not token:
        return ""
    fn = getattr(context, "protect_secret", None)
    if callable(fn):
        try:
            return fn(token) or token
        except Exception:
            return token
    return token


def _parent_code(
    context: HubContext,
    child: HubAccount,
    names: dict[str, str],
    lock: threading.Lock,
) -> str:
    parent = _parent_for(context, child)
    if parent is None:
        return ""
    with lock:
        cached = names.get(parent.id, "")
    if cached:
        return _protect(context, cached)
    return ""


def _dec(value: float) -> str:
    text = f"{float(value):.8f}".rstrip("0").rstrip(".")
    return text or "0"


def _blocked(
    context: HubContext,
    account: HubAccount,
    message: str,
    *,
    kind: str,
    extra: dict[str, Any] | None = None,
) -> str:
    safe = scrub_secrets(message)
    data = extra or _empty_row(account, kind)
    context.result(
        f"{account.label}: {safe}",
        kind=kind,
        status="blocked",
        account_id=account.id,
        data=data,
    )
    context.account_state(account.id, status="blocked", stage="blocked", message=safe)
    return "blocked"


def _failed(context: HubContext, account: HubAccount, message: str, *, kind: str) -> str:
    safe = scrub_secrets(message)
    context.result(
        f"{account.label}: {safe}",
        kind=kind,
        status="failed",
        account_id=account.id,
        data=_empty_row(account, kind),
    )
    context.account_state(account.id, status="failed", stage="automation_failed", message=safe)
    return "failed"


def _fail_unknown(context: HubContext, account: HubAccount, *, kind: str) -> None:
    _failed(context, account, "Ошибка обработки аккаунта", kind=kind)


def _empty_row(account: HubAccount, kind: str) -> dict[str, Any]:
    persona = persona_for(account.id)
    if kind == "account_snapshot":
        return {
            "username": "",
            "strategy": style_label(persona.style),
            "balance": "0",
            "bets": 0,
            "wallet_linked": False,
            "session": False,
        }
    return {
        "username": "",
        "strategy": style_label(persona.style),
        "bets": 0,
        "balance": "0",
        "wallet_linked": False,
        "referred": False,
    }
