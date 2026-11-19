"""Local demo password login and wallet-signature authentication."""
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import jwt
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import chain
from .config import settings

_nonces: dict[str, tuple[str, float]] = {}  # use Redis/Postgres in production
bearer = HTTPBearer()
_PASSWORD_SALT = secrets.token_bytes(16)
_PASSWORD_ROUNDS = 310_000
_OWNER_EMAIL = "owner@demo.mzansihealthchain.local"
_OWNER_PASSWORD = "OwnerDemo2026!"
_REQUESTER_EMAIL = "requester@demo.mzansihealthchain.local"
_REQUESTER_PASSWORD = "RequesterDemo2026!"


@dataclass(frozen=True)
class DemoAccount:
    email: str
    role: str
    password_digest: bytes


def _password_digest(password: str) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        _PASSWORD_SALT,
        _PASSWORD_ROUNDS,
    )


def _build_demo_accounts() -> dict[str, DemoAccount]:
    accounts = (
        DemoAccount(
            _OWNER_EMAIL,
            "patient",
            _password_digest(_OWNER_PASSWORD),
        ),
        DemoAccount(
            _REQUESTER_EMAIL,
            "clinician",
            _password_digest(_REQUESTER_PASSWORD),
        ),
    )
    return {account.email: account for account in accounts if account.email}


_DEMO_ACCOUNTS = _build_demo_accounts()


def _remote_demo_accounts() -> dict[str, DemoAccount]:
    configured = (
        (
            settings.demo_owner_email,
            settings.demo_owner_password,
            "patient",
        ),
        (
            settings.demo_requester_email,
            settings.demo_requester_password,
            "clinician",
        ),
    )

    return {
        email.strip().casefold(): DemoAccount(
            email=email.strip().casefold(),
            role=role,
            password_digest=_password_digest(password),
        )
        for email, password, role in configured
        if email.strip() and password
    }


def _is_local_rpc() -> bool:
    hostname = urlsplit(settings.rpc_url).hostname
    return hostname in ("localhost", "127.0.0.1", "::1")


def _demo_auth_is_enabled() -> bool:
    return settings.demo_auth_enabled and _is_local_rpc()


def _get_demo_accounts() -> dict[str, DemoAccount]:
    if not settings.demo_auth_enabled:
        return {}

    if _is_local_rpc():
        return _DEMO_ACCOUNTS

    if settings.demo_auth_allow_remote:
        return _remote_demo_accounts()

    return {}

def _local_chain_id() -> int:
    return chain.w3.eth.chain_id


def _new_token(subject: str, role: str, **claims) -> str:
    return jwt.encode(
        {"sub": subject, "role": role, "exp": int(time.time()) + 3600, **claims},
        settings.jwt_secret,
        algorithm="HS256",
    )


def verify_email_login(email: str, password: str, role: str) -> str:
    accounts = _get_demo_accounts()

    if not accounts:
        raise HTTPException(403, "Email/password demo sign-in is disabled.")

    account = accounts.get(email.strip().casefold())
    digest = _password_digest(password)

    if (
        not account
        or not hmac.compare_digest(digest, account.password_digest)
        or account.role != role
    ):
        raise HTTPException(401, "Invalid email, password, or account type.")

    return _new_token(
        account.email,
        account.role,
        email=account.email,
        auth_method="password",
        wallet=None,
    )

def _demo_wallet_account(user: dict, address: str) -> DemoAccount:
    if user.get("auth_method") != "password":
        raise HTTPException(403, "Wallet linking is available only for demo accounts.")

    email = str(user.get("email", "")).strip().casefold()
    account = _get_demo_accounts().get(email)

    if not account:
        raise HTTPException(403, "No demo account is configured for this user.")

    chain_id = _local_chain_id()

    if _is_local_rpc():
        if chain_id != 31337:
            raise HTTPException(403, "Demo wallet linking requires local Anvil chain 31337.")
    elif settings.demo_auth_allow_remote:
        if chain_id != 43113:
            raise HTTPException(403, "Remote demo wallet linking requires Avalanche Fuji.")
    else:
        raise HTTPException(403, "Remote demo wallet linking is disabled.")

    if chain.role_of(address) != account.role:
        raise HTTPException(
            403,
            f"Connect a wallet registered as a {account.role} on the configured chain.",
        )

    return account

def issue_wallet_link_nonce(user: dict, address: str) -> str:
    account = _demo_wallet_account(user, address)
    email = account.email

    nonce = secrets.token_hex(16)
    key = f"link:{email}:{address.lower()}"
    message = f"Link wallet {address.lower()} to MzansiHealthChain account {email}. Nonce: {nonce}"
    _nonces[key] = (nonce, time.time() + 300)
    return message


def verify_wallet_link(user: dict, address: str, signature: str) -> str:
    account = _demo_wallet_account(user, address)
    email = account.email

    key = f"link:{email}:{address.lower()}"
    entry = _nonces.pop(key, None)
    if not entry or entry[1] < time.time():
        raise HTTPException(401, "Wallet-link nonce missing or expired.")

    message = f"Link wallet {address.lower()} to MzansiHealthChain account {email}. Nonce: {entry[0]}"
    recovered = Account.recover_message(encode_defunct(text=message), signature=signature)
    if recovered.lower() != address.lower():
        raise HTTPException(401, "Invalid wallet-link signature.")

    return _new_token(
        account.email,
        account.role,
        email=account.email,
        auth_method="password",
        wallet=address.lower(),
    )


def linked_wallet(user: dict) -> str:
    wallet = user.get("wallet")
    if not wallet:
        raise HTTPException(409, "Connect your Core Wallet in Settings before using this feature.")
    return str(wallet)


def login_message(nonce: str) -> str:
    return f"Sign in to MzansiHealthChain. Nonce: {nonce}"


def issue_nonce(address: str) -> str:
    nonce = secrets.token_hex(16)
    _nonces[address.lower()] = (nonce, time.time() + 300)
    return login_message(nonce)


def verify_login(address: str, signature: str) -> str:
    entry = _nonces.pop(address.lower(), None)
    if not entry or entry[1] < time.time():
        raise HTTPException(401, "nonce missing or expired")
    recovered = Account.recover_message(encode_defunct(text=login_message(entry[0])), signature=signature)
    if recovered.lower() != address.lower():
        raise HTTPException(401, "bad signature")
    role = chain.role_of(address)
    if role == "none":
        raise HTTPException(403, "wallet not registered on-chain")
    return _new_token(address.lower(), role, auth_method="wallet", wallet=address.lower())


def current_user(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    try:
        return jwt.decode(cred.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid token")
