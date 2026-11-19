
import os
import time

import jwt
import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import HTTPException

from app import auth


PATIENT_EMAIL = "participant@mzansihealthchain.com"
CLINICIAN_EMAIL = "clinician@mzansihealthchain.com"

# Test-only passwords. These are not production credentials.
PATIENT_PASSWORD = "Test-Only-Patient-Password!"
CLINICIAN_PASSWORD = "Test-Only-Clinician-Password!"


def _sign(acct, message: str):
    return acct.sign_message(encode_defunct(text=message)).signature


def _configure_demo_auth(monkeypatch, remote=False):
    monkeypatch.setattr(auth.settings, "demo_auth_enabled", True)
    monkeypatch.setattr(auth.settings, "demo_auth_allow_remote", remote)
    monkeypatch.setattr(
        auth.settings, "demo_owner_password", PATIENT_PASSWORD
    )
    monkeypatch.setattr(
        auth.settings, "demo_requester_password", CLINICIAN_PASSWORD
    )
    monkeypatch.setattr(
        auth.settings,
        "rpc_url",
        (
            "https://api.avax-test.network/ext/bc/C/rpc"
            if remote
            else "http://127.0.0.1:8545"
        ),
    )


def _login(email, password, role):
    return auth.verify_email_login(email, password, role)


def test_login_issues_jwt_with_onchain_role(monkeypatch):
    monkeypatch.setattr(auth.chain, "role_of", lambda a: "clinician")
    acct = Account.create()
    token = auth.verify_login(
        acct.address, _sign(acct, auth.issue_nonce(acct.address))
    )
    claims = jwt.decode(
        token, os.environ["JWT_SECRET"], algorithms=["HS256"]
    )
    assert claims["sub"] == acct.address.lower()
    assert claims["role"] == "clinician"


def test_nonce_cannot_be_replayed(monkeypatch):
    monkeypatch.setattr(auth.chain, "role_of", lambda a: "patient")
    acct = Account.create()
    signature = _sign(acct, auth.issue_nonce(acct.address))
    auth.verify_login(acct.address, signature)
    with pytest.raises(HTTPException) as exc:
        auth.verify_login(acct.address, signature)
    assert exc.value.status_code == 401


def test_signature_from_other_wallet_is_rejected(monkeypatch):
    monkeypatch.setattr(auth.chain, "role_of", lambda a: "patient")
    victim, attacker = Account.create(), Account.create()
    message = auth.issue_nonce(victim.address)
    with pytest.raises(HTTPException) as exc:
        auth.verify_login(victim.address, _sign(attacker, message))
    assert exc.value.status_code == 401


def test_expired_nonce_is_rejected(monkeypatch):
    monkeypatch.setattr(auth.chain, "role_of", lambda a: "patient")
    acct = Account.create()
    auth.issue_nonce(acct.address)
    auth._nonces[acct.address.lower()] = ("expired", time.time() - 1)
    with pytest.raises(HTTPException) as exc:
        auth.verify_login(acct.address, "invalid")
    assert exc.value.status_code == 401


def test_unregistered_wallet_is_rejected(monkeypatch):
    monkeypatch.setattr(auth.chain, "role_of", lambda a: "none")
    acct = Account.create()
    with pytest.raises(HTTPException) as exc:
        auth.verify_login(
            acct.address, _sign(acct, auth.issue_nonce(acct.address))
        )
    assert exc.value.status_code == 403


def test_patient_demo_login(monkeypatch):
    _configure_demo_auth(monkeypatch)
    token = _login(PATIENT_EMAIL, PATIENT_PASSWORD, "patient")
    claims = jwt.decode(
        token, auth.settings.jwt_secret, algorithms=["HS256"]
    )
    assert claims["sub"] == PATIENT_EMAIL
    assert claims["email"] == PATIENT_EMAIL
    assert claims["role"] == "patient"
    assert claims["auth_method"] == "password"


def test_clinician_demo_login(monkeypatch):
    _configure_demo_auth(monkeypatch)
    token = _login(CLINICIAN_EMAIL, CLINICIAN_PASSWORD, "clinician")
    claims = jwt.decode(
        token, auth.settings.jwt_secret, algorithms=["HS256"]
    )
    assert claims["sub"] == CLINICIAN_EMAIL
    assert claims["role"] == "clinician"


@pytest.mark.parametrize(
    "email,password,role",
    [
        (PATIENT_EMAIL, "Wrong-Password!", "patient"),
        (CLINICIAN_EMAIL, "Wrong-Password!", "clinician"),
        (PATIENT_EMAIL, PATIENT_PASSWORD, "clinician"),
        (CLINICIAN_EMAIL, CLINICIAN_PASSWORD, "patient"),
        ("unknown@mzansihealthchain.com", PATIENT_PASSWORD, "patient"),
    ],
)
def test_invalid_demo_login_is_rejected(
    monkeypatch, email, password, role
):
    _configure_demo_auth(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        _login(email, password, role)
    assert exc.value.status_code == 401


def test_demo_login_disabled_by_default(monkeypatch):
    monkeypatch.setattr(auth.settings, "demo_auth_enabled", False)
    with pytest.raises(HTTPException) as exc:
        _login(PATIENT_EMAIL, PATIENT_PASSWORD, "patient")
    assert exc.value.status_code == 403


def test_remote_demo_login_disabled_without_remote_flag(monkeypatch):
    _configure_demo_auth(monkeypatch, remote=False)
    monkeypatch.setattr(
        auth.settings, "rpc_url",
        "https://api.avax-test.network/ext/bc/C/rpc",
    )
    with pytest.raises(HTTPException) as exc:
        _login(PATIENT_EMAIL, PATIENT_PASSWORD, "patient")
    assert exc.value.status_code == 403


def test_remote_patient_demo_login(monkeypatch):
    _configure_demo_auth(monkeypatch, remote=True)
    monkeypatch.setattr(auth, "_local_chain_id", lambda: 43113)
    token = _login(PATIENT_EMAIL, PATIENT_PASSWORD, "patient")
    claims = jwt.decode(
        token, auth.settings.jwt_secret, algorithms=["HS256"]
    )
    assert claims["role"] == "patient"


def test_remote_clinician_demo_login(monkeypatch):
    _configure_demo_auth(monkeypatch, remote=True)
    monkeypatch.setattr(auth, "_local_chain_id", lambda: 43113)
    token = _login(CLINICIAN_EMAIL, CLINICIAN_PASSWORD, "clinician")
    claims = jwt.decode(
        token, auth.settings.jwt_secret, algorithms=["HS256"]
    )
    assert claims["role"] == "clinician"

def test_remote_demo_login_rejects_non_fuji_chain(monkeypatch):
    _configure_demo_auth(monkeypatch, remote=True)
    monkeypatch.setattr(auth, "_local_chain_id", lambda: 1)

    with pytest.raises(HTTPException) as exc:
        _login(PATIENT_EMAIL, PATIENT_PASSWORD, "patient")

    assert exc.value.status_code == 403

def test_remote_wrong_password_is_rejected(monkeypatch):
    _configure_demo_auth(monkeypatch, remote=True)
    monkeypatch.setattr(auth, "_local_chain_id", lambda: 43113)
    with pytest.raises(HTTPException) as exc:
        _login(PATIENT_EMAIL, "Wrong-Password!", "patient")
    assert exc.value.status_code == 401


def test_wallet_link_requires_password_authenticated_demo_user():
    with pytest.raises(HTTPException) as exc:
        auth._demo_wallet_account(
            {"auth_method": "wallet", "email": PATIENT_EMAIL},
            Account.create().address,
        )
    assert exc.value.status_code == 403


def test_wallet_link_requires_configured_demo_account(monkeypatch):
    _configure_demo_auth(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        auth._demo_wallet_account(
            {"auth_method": "password", "email": "unknown@example.com"},
            Account.create().address,
        )
    assert exc.value.status_code == 403


def test_wallet_link_requires_registered_role(monkeypatch):
    _configure_demo_auth(monkeypatch)
    monkeypatch.setattr(auth, "_local_chain_id", lambda: 31337)
    monkeypatch.setattr(auth.chain, "role_of", lambda a: "clinician")
    user = {"auth_method": "password", "email": PATIENT_EMAIL}
    with pytest.raises(HTTPException) as exc:
        auth._demo_wallet_account(user, Account.create().address)
    assert exc.value.status_code == 403


def test_wallet_link_nonce_and_signature(monkeypatch):
    _configure_demo_auth(monkeypatch)
    monkeypatch.setattr(auth, "_local_chain_id", lambda: 31337)
    acct = Account.create()
    monkeypatch.setattr(auth.chain, "role_of", lambda a: "patient")
    user = {"auth_method": "password", "email": PATIENT_EMAIL}
    message = auth.issue_wallet_link_nonce(user, acct.address)
    signature = _sign(acct, message)
    token = auth.verify_wallet_link(user, acct.address, signature)
    claims = jwt.decode(
        token, auth.settings.jwt_secret, algorithms=["HS256"]
    )
    assert claims["wallet"] == acct.address.lower()
    assert claims["role"] == "patient"


def test_wallet_link_nonce_cannot_be_replayed(monkeypatch):
    _configure_demo_auth(monkeypatch)
    monkeypatch.setattr(auth, "_local_chain_id", lambda: 31337)
    acct = Account.create()
    monkeypatch.setattr(auth.chain, "role_of", lambda a: "patient")
    user = {"auth_method": "password", "email": PATIENT_EMAIL}
    message = auth.issue_wallet_link_nonce(user, acct.address)
    signature = _sign(acct, message)
    auth.verify_wallet_link(user, acct.address, signature)
    with pytest.raises(HTTPException) as exc:
        auth.verify_wallet_link(user, acct.address, signature)
    assert exc.value.status_code == 401


def test_linked_wallet_requires_wallet():
    with pytest.raises(HTTPException) as exc:
        auth.linked_wallet({"wallet": None})
    assert exc.value.status_code == 409


def test_linked_wallet_returns_wallet():
    assert auth.linked_wallet({"wallet": "0x123"}) == "0x123"
