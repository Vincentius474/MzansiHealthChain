import os
import time

import jwt
import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import HTTPException

from app import auth


def _sign(acct, message: str):
    return acct.sign_message(encode_defunct(text=message)).signature


def test_login_issues_jwt_with_onchain_role(monkeypatch):
    monkeypatch.setattr(auth.chain, "role_of", lambda a: "clinician")
    acct = Account.create()
    token = auth.verify_login(acct.address, _sign(acct, auth.issue_nonce(acct.address)))
    claims = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
    assert claims["sub"] == acct.address.lower() and claims["role"] == "clinician"


def test_nonce_cannot_be_replayed(monkeypatch):
    monkeypatch.setattr(auth.chain, "role_of", lambda a: "patient")
    acct = Account.create()
    sig = _sign(acct, auth.issue_nonce(acct.address))
    auth.verify_login(acct.address, sig)
    with pytest.raises(HTTPException) as e:
        auth.verify_login(acct.address, sig)
    assert e.value.status_code == 401


def test_signature_from_other_wallet_is_rejected(monkeypatch):
    monkeypatch.setattr(auth.chain, "role_of", lambda a: "patient")
    victim, attacker = Account.create(), Account.create()
    msg = auth.issue_nonce(victim.address)
    with pytest.raises(HTTPException) as e:
        auth.verify_login(victim.address, _sign(attacker, msg))
    assert e.value.status_code == 401


def test_expired_nonce_is_rejected(monkeypatch):
    monkeypatch.setattr(auth.chain, "role_of", lambda a: "patient")
    acct = Account.create()
    msg = auth.issue_nonce(acct.address)
    nonce, _ = auth._nonces[acct.address.lower()]
    auth._nonces[acct.address.lower()] = (nonce, time.time() - 1)
    with pytest.raises(HTTPException) as e:
        auth.verify_login(acct.address, _sign(acct, msg))
    assert e.value.status_code == 401


def test_unregistered_wallet_gets_403(monkeypatch):
    monkeypatch.setattr(auth.chain, "role_of", lambda a: "none")
    acct = Account.create()
    with pytest.raises(HTTPException) as e:
        auth.verify_login(acct.address, _sign(acct, auth.issue_nonce(acct.address)))
    assert e.value.status_code == 403


@pytest.mark.parametrize(
    ("email", "password", "role"),
    [
        ("owner@demo.mzansihealthchain.local", "OwnerDemo2026!", "patient"),
        ("requester@demo.mzansihealthchain.local", "RequesterDemo2026!", "clinician"),
    ],
)
def test_demo_email_login_returns_unlinked_session(email, password, role):
    token = auth.verify_email_login(
        email,
        password,
        role,
    )
    claims = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
    assert claims["sub"] == email
    assert claims["role"] == role
    assert claims["wallet"] is None


@pytest.mark.parametrize(
    ("email", "password", "role"),
    [
        ("owner@demo.mzansihealthchain.local", "wrong-password", "patient"),
        ("owner@demo.mzansihealthchain.local", "OwnerDemo2026!", "clinician"),
        ("unknown@demo.mzansihealthchain.local", "OwnerDemo2026!", "patient"),
    ],
)
def test_demo_email_login_rejects_invalid_credentials(email, password, role):
    with pytest.raises(HTTPException) as e:
        auth.verify_email_login(email, password, role)
    assert e.value.status_code == 401


def test_demo_email_login_is_disabled_for_nonlocal_rpc(monkeypatch):
    monkeypatch.setattr(auth.settings, "rpc_url", "https://api.avax-test.network/ext/bc/C/rpc")
    with pytest.raises(HTTPException) as e:
        auth.verify_email_login("owner@demo.mzansihealthchain.local", "OwnerDemo2026!", "patient")
    assert e.value.status_code == 403


@pytest.mark.parametrize(
    ("email", "required_role", "actual_role"),
    [
        ("owner@demo.mzansihealthchain.local", "patient", "clinician"),
        ("owner@demo.mzansihealthchain.local", "patient", "none"),
        ("requester@demo.mzansihealthchain.local", "clinician", "patient"),
    ],
)
def test_demo_wallet_link_rejects_wallet_with_wrong_role(email, required_role, actual_role, monkeypatch):
    user = {"email": email, "auth_method": "password"}
    account = Account.create()
    monkeypatch.setattr(auth, "_local_chain_id", lambda: 31337)
    monkeypatch.setattr(auth.chain, "role_of", lambda address: actual_role)
    with pytest.raises(HTTPException) as e:
        auth.issue_wallet_link_nonce(user, account.address)
    assert e.value.status_code == 403
    assert required_role in e.value.detail


@pytest.mark.parametrize(
    ("email", "role"),
    [
        ("owner@demo.mzansihealthchain.local", "patient"),
        ("requester@demo.mzansihealthchain.local", "clinician"),
    ],
)
def test_demo_wallet_link_verifies_signature_and_chain_role(email, role, monkeypatch):
    account = Account.create()
    user = {"email": email, "auth_method": "password"}
    monkeypatch.setattr(auth, "_local_chain_id", lambda: 31337)
    monkeypatch.setattr(auth.chain, "role_of", lambda address: role)

    message = auth.issue_wallet_link_nonce(user, account.address)
    token = auth.verify_wallet_link(user, account.address, _sign(account, message))
    claims = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
    assert claims["email"] == user["email"]
    assert claims["role"] == role
    assert claims["wallet"] == account.address.lower()


def test_demo_wallet_link_nonce_cannot_be_replayed(monkeypatch):
    account = Account.create()
    user = {"email": "owner@demo.mzansihealthchain.local", "auth_method": "password"}
    monkeypatch.setattr(auth, "_local_chain_id", lambda: 31337)
    monkeypatch.setattr(auth.chain, "role_of", lambda address: "patient")
    message = auth.issue_wallet_link_nonce(user, account.address)
    signature = _sign(account, message)
    auth.verify_wallet_link(user, account.address, signature)

    with pytest.raises(HTTPException) as e:
        auth.verify_wallet_link(user, account.address, signature)
    assert e.value.status_code == 401


def test_linked_wallet_requires_a_wallet_claim():
    with pytest.raises(HTTPException) as e:
        auth.linked_wallet({"role": "patient"})
    assert e.value.status_code == 409


def test_remote_demo_email_login_succeeds_on_fuji(monkeypatch):
    monkeypatch.setattr(
        auth.settings, "rpc_url",
        "https://api.avax-test.network/ext/bc/C/rpc",
    )
    monkeypatch.setattr(auth.settings, "demo_auth_enabled", True)
    monkeypatch.setattr(auth.settings, "demo_auth_allow_remote", True)
    monkeypatch.setattr(auth.settings, "demo_owner_email", "fuji-owner@example.test")
    monkeypatch.setattr(auth.settings, "demo_owner_password", "Test-Only-Owner-Password!")

    token = auth.verify_email_login(
        "fuji-owner@example.test",
        "Test-Only-Owner-Password!",
        "patient",
    )
    claims = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])

    assert claims["sub"] == "fuji-owner@example.test"
    assert claims["role"] == "patient"
    assert claims["wallet"] is None


def test_remote_demo_email_login_rejects_wrong_password(monkeypatch):
    monkeypatch.setattr(
        auth.settings, "rpc_url",
        "https://api.avax-test.network/ext/bc/C/rpc",
    )
    monkeypatch.setattr(auth.settings, "demo_auth_enabled", True)
    monkeypatch.setattr(auth.settings, "demo_auth_allow_remote", True)
    monkeypatch.setattr(auth.settings, "demo_owner_email", "fuji-owner@example.test")
    monkeypatch.setattr(auth.settings, "demo_owner_password", "Test-Only-Owner-Password!")

    with pytest.raises(HTTPException) as e:
        auth.verify_email_login(
            "fuji-owner@example.test",
            "incorrect-password",
            "patient",
        )

    assert e.value.status_code == 401


def test_remote_demo_wallet_link_requires_fuji_role(monkeypatch):
    monkeypatch.setattr(
        auth.settings, "rpc_url",
        "https://api.avax-test.network/ext/bc/C/rpc",
    )
    monkeypatch.setattr(auth.settings, "demo_auth_enabled", True)
    monkeypatch.setattr(auth.settings, "demo_auth_allow_remote", True)
    monkeypatch.setattr(auth.settings, "demo_owner_email", "fuji-owner@example.test")
    monkeypatch.setattr(auth.settings, "demo_owner_password", "Test-Only-Owner-Password!")
    monkeypatch.setattr(auth, "_local_chain_id", lambda: 43113)
    monkeypatch.setattr(auth.chain, "role_of", lambda address: "clinician")

    user = {
        "email": "fuji-owner@example.test",
        "auth_method": "password",
    }

    account = Account.create()

    with pytest.raises(HTTPException) as e:
        auth.issue_wallet_link_nonce(user, account.address)

    assert e.value.status_code == 403
    assert "patient" in e.value.detail
