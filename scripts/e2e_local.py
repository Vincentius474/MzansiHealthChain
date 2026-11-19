#!/usr/bin/env python3
"""End-to-end check against LOCAL anvil + the running backend. No browser needed.

Prereqs: `make anvil`, `make deploy-local`, `make seed-local`, `make backend` (and Ollama for the
summary step). Run: python scripts/e2e_local.py [--require-ai]

Flow: requester asks for scoped access -> patient approves on-chain ->
encrypt+store -> AI summary + audit -> patient revokes -> 403 + denied audit -> access restored.
"""
import json
import pathlib
import sys

import httpx
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

ROOT = pathlib.Path(__file__).resolve().parent.parent
API, RPC = "http://127.0.0.1:8000", "http://127.0.0.1:8545"
PATIENT_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"    # anvil #1 (public)
CLINICIAN_KEY = "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6"  # anvil #3 (public)
REQUIRE_AI = "--require-ai" in sys.argv

w3 = Web3(Web3.HTTPProvider(RPC))
dep = json.loads((ROOT / "contracts" / "deployments" / "31337.json").read_text())
patient, clinician = Account.from_key(PATIENT_KEY), Account.from_key(CLINICIAN_KEY)


def fn(name, inputs, outputs=(), mut="nonpayable"):
    return {"type": "function", "name": name, "stateMutability": mut,
            "inputs": [{"name": n, "type": t} for n, t in inputs],
            "outputs": [{"name": "", "type": t} for t in outputs]}


access = w3.eth.contract(address=dep["AccessControl"], abi=[
    fn("addRecord", [("patient", "address"), ("h", "bytes32"), ("ref", "string")], ["uint256"])])
consent = w3.eth.contract(address=dep["ConsentManagement"], abi=[
    fn("grant", [("provider", "address"), ("expiry", "uint64")]),
    fn("revoke", [("provider", "address")]),
    fn("consentExpiry", [("patient", "address"), ("provider", "address")], ["uint64"], "view")])
audit = w3.eth.contract(address=dep["AuditLog"], abi=[{
    "type": "event", "name": "AccessLogged", "anonymous": False, "inputs": [
        {"name": "patient", "type": "address", "indexed": True},
        {"name": "provider", "type": "address", "indexed": True},
        {"name": "recordId", "type": "uint256", "indexed": True},
        {"name": "actionHash", "type": "bytes32", "indexed": False},
        {"name": "timestamp", "type": "uint64", "indexed": False}]}])


def send(call, acct):
    tx = call.build_transaction({"from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address),
                                 "chainId": w3.eth.chain_id})
    receipt = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(acct.sign_transaction(tx).raw_transaction))
    assert receipt.status == 1, "transaction reverted"
    return receipt


def login(acct):
    msg = httpx.post(f"{API}/auth/nonce", json={"address": acct.address}).json()["message"]
    sig = acct.sign_message(encode_defunct(text=msg)).signature.to_0x_hex()
    r = httpx.post(f"{API}/auth/login", json={"address": acct.address, "signature": sig})
    return r


def step(msg):
    print(f"\n== {msg}")


def audit_actions():
    logs = audit.events.AccessLogged().get_logs(from_block=0)
    return [l["args"]["actionHash"] for l in logs]


assert httpx.get(f"{API}/health").json() == {"ok": True}

step("unregistered wallet is refused")
assert login(Account.create()).status_code == 403
print("ok: 403")

step("clinician logs in with wallet signature")
r = login(clinician)
assert r.status_code == 200, r.text
H = {"Authorization": f"Bearer {r.json()['token']}"}
print("ok: JWT issued")

step("patient logs in and requester submits a scoped access request")
r = login(patient)
assert r.status_code == 200, r.text
PH = {"Authorization": f"Bearer {r.json()['token']}"}
r = httpx.post(f"{API}/access-requests", headers=H, json={
    "patient": patient.address,
    "purpose": "Coordinate treatment and medication review.",
    "categories": ["allergies", "diagnoses", "medications", "visit_notes"],
    "duration_days": 30,
    "urgent": False,
})
assert r.status_code == 200, r.text
request_id = r.json()["id"]
print("ok: request submitted", request_id)

step("patient approves the request with an on-chain consent transaction")
expiry = w3.eth.get_block("latest").timestamp + 30 * 86400
chain_expiry = max(expiry, consent.functions.consentExpiry(patient.address, clinician.address).call())
send(consent.functions.grant(clinician.address, chain_expiry), patient)
r = httpx.post(f"{API}/access-requests/{request_id}/approve", headers=PH, json={
    "categories": ["allergies", "diagnoses", "medications", "visit_notes"],
    "expiry": expiry,
    "chain_expiry": chain_expiry,
})
assert r.status_code == 200, r.text
print("ok: categories and expiry recorded")

step("encrypt + store a record, then anchor it on-chain from the clinician wallet")
enc = httpx.post(f"{API}/records/encrypt", headers=H,
                 json={"patient": patient.address, "content": "2026-11-18: Type 2 diabetes. Metformin 500mg BD. Allergic to penicillin.",
                       "title": "Medication and allergy review", "category": "visit_notes",
                       "record_date": "2026-11-18"}).json()
send(access.functions.addRecord(patient.address, enc["hash"], enc["ref"]), clinician)
print("ok: record anchored", enc["hash"][:18], "...")

step("AI summary (consent verified on-chain, decrypted locally, access audited)")
before = len(audit_actions())
r = httpx.post(f"{API}/agent/summary", headers=H, timeout=180,
               json={"patient": patient.address, "question": "Summarise this patient's history."})
if r.status_code == 200:
    body = r.json()
    print("summary:", body["summary"])
    print("trace:", *body["trace"], sep="\n  - ")
    assert len(audit_actions()) > before, "no audit event written"
    print("ok: audit event on-chain")
elif REQUIRE_AI:
    sys.exit(f"summary failed: {r.status_code} {r.text}")
else:
    print(f"SKIPPED (status {r.status_code}). Is Ollama running with the model pulled? Re-run with --require-ai to fail instead.")

step("patient revokes consent -> clinician is denied and the attempt is audited")
send(consent.functions.revoke(clinician.address), patient)
r = httpx.post(f"{API}/permissions/revoke", headers=PH, params={"provider": clinician.address})
assert r.status_code == 200, r.text
before = len(audit_actions())
r = httpx.post(f"{API}/agent/summary", headers=H, timeout=60,
               json={"patient": patient.address, "question": "Summarise."})
assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
assert len(audit_actions()) == before + 1, "denied attempt not audited"
assert Web3.keccak(text="ACCESS_DENIED") in audit_actions()
print("ok: 403 + ACCESS_DENIED logged")

step("restore consent so the demo state is usable again")
expiry = w3.eth.get_block("latest").timestamp + 30 * 86400
r = httpx.post(f"{API}/access-requests", headers=H, json={
    "patient": patient.address,
    "purpose": "Continue treatment and medication follow-up.",
    "categories": ["allergies", "diagnoses", "medications", "visit_notes"],
    "duration_days": 30,
    "urgent": False,
})
assert r.status_code == 200, r.text
request_id = r.json()["id"]
chain_expiry = max(expiry, consent.functions.consentExpiry(patient.address, clinician.address).call())
send(consent.functions.grant(clinician.address, chain_expiry), patient)
r = httpx.post(f"{API}/access-requests/{request_id}/approve", headers=PH, json={
    "categories": ["allergies", "diagnoses", "medications", "visit_notes"],
    "expiry": expiry,
    "chain_expiry": chain_expiry,
})
assert r.status_code == 200, r.text
print("\nALL CHECKS PASSED")
