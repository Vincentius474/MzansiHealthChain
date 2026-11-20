import httpx
import pytest
import time
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from app import auth, crypto, workflow
from app.main import app

P = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
D = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"

PATIENT_EMAIL = "participant@mzansihealthchain.com"
PATIENT_PASSWORD = "Test-Only-Patient-Password!"

def configure_patient_demo_auth(monkeypatch):
    monkeypatch.setattr(auth.settings, "demo_auth_enabled", True)
    monkeypatch.setattr(auth.settings, "demo_auth_allow_remote", False)
    monkeypatch.setattr(
        auth.settings, "demo_owner_password", PATIENT_PASSWORD
    )
    monkeypatch.setattr(
        auth.settings, "demo_requester_password",
        "Test-Only-Clinician-Password!"
    )


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],
)
def test_local_demo_cors_allows_loopback_frontend_ports(client, origin):
    response = client.options(
        "/auth/email-login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_local_demo_cors_rejects_nonlocal_origin(client):
    response = client.options(
        "/auth/email-login",
        headers={
            "Origin": "https://example.test",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def as_user(address, role):
    app.dependency_overrides[auth.current_user] = lambda: {
        "sub": address.lower(), "role": role, "wallet": address.lower(), "auth_method": "wallet",
    }


def approve_scope(patient, requester, categories=("allergies",), days=2):
    request = workflow.create_request(
        patient, requester, "Care coordination for an active treatment plan.",
        list(categories), days, False,
    )
    workflow.approve_request(
        request["id"], list(categories), int(time.time()) + days * 86400,
    )


def test_me(client):
    as_user(D, "clinician")
    assert client.get("/auth/me").json() == {
        "email": None, "address": D.lower(), "role": "clinician", "wallet_linked": True,
    }
def test_email_login_creates_unlinked_session(client, monkeypatch):
    configure_patient_demo_auth(monkeypatch)

    response = client.post("/auth/email-login", json={
        "email": PATIENT_EMAIL,
        "password": PATIENT_PASSWORD,
        "role": "patient",
    })
    assert response.status_code == 200

    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {response.json()['token']}"},
    )
    assert me.json() == {
        "email": PATIENT_EMAIL,
        "address": None,
        "role": "patient",
        "wallet_linked": False,
    }


def test_unlinked_session_cannot_access_chain_data(client, monkeypatch):
    configure_patient_demo_auth(monkeypatch)

    token = auth.verify_email_login(
        PATIENT_EMAIL, PATIENT_PASSWORD, "patient"
    )
    response = client.get(
        f"/audit/{P}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409
    assert "Core Wallet in Settings" in response.json()["detail"]


def test_wallet_can_be_linked_from_settings(client, monkeypatch):
    configure_patient_demo_auth(monkeypatch)

    account = Account.from_key(
        "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
    )
    token = auth.verify_email_login(
        PATIENT_EMAIL, PATIENT_PASSWORD, "patient"
    )
    headers = {"Authorization": f"Bearer {token}"}

    monkeypatch.setattr(auth, "_local_chain_id", lambda: 31337)
    monkeypatch.setattr(auth.chain, "role_of", lambda address: "patient")

    nonce = client.post(
        "/auth/wallet/nonce",
        json={"address": account.address},
        headers=headers,
    )
    assert nonce.status_code == 200

    signature = account.sign_message(
        encode_defunct(text=nonce.json()["message"])
    ).signature.hex()

    linked = client.post(
        "/auth/wallet/link",
        json={"address": account.address, "signature": signature},
        headers=headers,
    )
    assert linked.status_code == 200

    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {linked.json()['token']}"},
    )
    assert me.json()["address"] == account.address.lower()
    assert me.json()["wallet_linked"] is True

def test_records_are_provider_only(client):
    as_user(P, "patient")
    assert client.get(f"/records/{P}").status_code == 403


def test_records_require_consent(client, monkeypatch):
    as_user(D, "clinician")
    monkeypatch.setattr("app.main.chain.can_access", lambda prov, pat: False)
    assert client.get(f"/records/{P}").status_code == 403


def test_records_hide_storage_refs(client, monkeypatch):
    as_user(D, "clinician")
    approve_scope(P, D)
    monkeypatch.setattr("app.main.chain.can_access", lambda prov, pat: True)
    monkeypatch.setattr("app.main.chain.get_records", lambda prov, pat: [
        {"id": 0, "hash": "ab" * 32, "ref": "ehr/secret-key", "added_by": D, "timestamp": 5}])
    workflow.save_record_metadata("ab" * 32, P, "allergies", "Allergies", "2026-01-01", D)
    monkeypatch.setattr("app.main.chain.log_access", lambda *args: "0xaudit")
    body = client.get(f"/records/{P}").json()
    assert body[0]["hash"] == "0x" + "ab" * 32
    assert "ref" not in body[0] and "secret-key" not in str(body)


def test_audit_trail_is_patient_only_and_own_only(client, monkeypatch):
    monkeypatch.setattr("app.main.chain.audit_trail", lambda pat: [{"action": "SUMMARY_REQUESTED"}])
    as_user(P, "patient")
    assert client.get(f"/audit/{P}").json() == [{"action": "SUMMARY_REQUESTED"}]
    assert client.get(f"/audit/{D}").status_code == 403       # someone else's trail
    as_user(D, "clinician")
    assert client.get(f"/audit/{P}").status_code == 403       # providers cannot read it


def test_invalid_address_is_422(client):
    as_user(D, "clinician")
    assert client.get("/records/not-an-address").status_code == 422
    assert client.post("/agent/summary", json={"patient": "nope"}).status_code == 422


def test_encrypt_requires_consent(client, monkeypatch):
    as_user(D, "clinician")
    monkeypatch.setattr("app.main.chain.can_access", lambda prov, pat: False)
    assert client.post("/records/encrypt", json={"patient": P, "content": "x"}).status_code == 403


def test_encrypt_returns_hash_and_ref(client, monkeypatch):
    as_user(D, "clinician")
    approve_scope(P, D, categories=("visit_notes",))
    monkeypatch.setattr("app.main.chain.can_access", lambda prov, pat: True)
    monkeypatch.setattr("app.main.chain.get_records", lambda *args: [])
    monkeypatch.setattr("app.main.storage.put", lambda blob: "ehr/test-ref")
    body = client.post("/records/encrypt", json={
        "patient": P, "content": "note", "category": "visit_notes",
        "title": "Visit note", "record_date": "2026-01-01",
    }).json()
    assert body["ref"] == "ehr/test-ref" and body["hash"].startswith("0x") and len(body["hash"]) == 66
    metadata = workflow.get_record_metadata(body["hash"])
    assert metadata["category"] == "visit_notes" and metadata["title"] == "Visit note"


def test_patient_can_encrypt_own_record_without_provider_consent(client, monkeypatch):
    as_user(P, "patient")
    monkeypatch.setattr("app.main.storage.put", lambda blob: "ehr/patient-record")
    response = client.post("/records/encrypt", json={
        "patient": P,
        "content": "My history",
        "title": "Personal history",
        "category": "diagnoses",
        "record_date": "2026-02-01",
    })
    assert response.status_code == 200
    assert workflow.get_record_metadata(response.json()["hash"])["created_by"] == P.lower()


def test_access_request_owner_decision_and_notifications(client, monkeypatch):
    as_user(D, "clinician")
    monkeypatch.setattr("app.main.chain.role_of", lambda address: "patient")
    created = client.post("/access-requests", json={
        "patient": P,
        "purpose": "Coordinate treatment and medication review.",
        "categories": ["medications", "allergies"],
        "duration_days": 14,
        "urgent": True,
    })
    assert created.status_code == 200
    request_id = created.json()["id"]

    as_user(P, "patient")
    inbox = client.get("/access-requests/inbox").json()
    assert inbox[0]["id"] == request_id and inbox[0]["urgent"] is True
    assert client.post(f"/access-requests/{request_id}/deny").status_code == 200

    as_user(D, "clinician")
    assert client.get("/access-requests/mine").json()[0]["status"] == "denied"
    assert client.get("/notifications").json()[0]["kind"] == "access_denied"


def test_access_approval_requires_matching_chain_consent_and_requested_scope(client, monkeypatch):
    as_user(D, "clinician")
    monkeypatch.setattr("app.main.chain.role_of", lambda address: "patient")
    created = client.post("/access-requests", json={
        "patient": P,
        "purpose": "Coordinate treatment and medication review.",
        "categories": ["medications", "allergies"],
        "duration_days": 30,
    }).json()

    as_user(P, "patient")
    expiry = int(time.time()) + 86400
    monkeypatch.setattr("app.main.chain.consent_expiry", lambda patient, provider: expiry)
    invalid = client.post(f"/access-requests/{created['id']}/approve", json={
        "categories": ["diagnoses"], "expiry": expiry, "chain_expiry": expiry,
    })
    assert invalid.status_code == 422
    approved = client.post(f"/access-requests/{created['id']}/approve", json={
        "categories": ["medications"], "expiry": expiry, "chain_expiry": expiry,
    })
    assert approved.status_code == 200
    assert workflow.allowed_categories(P, D) == {"medications"}


def test_record_content_requires_approved_category_and_logs_reads(client, monkeypatch):
    as_user(D, "clinician")
    approve_scope(P, D, categories=("allergies",))
    blob, digest = crypto.encrypt(b"Penicillin allergy.", P)
    workflow.save_record_metadata(digest, P, "allergies", "Allergy record", "2026-01-01", D)
    workflow.save_record_metadata("cd" * 32, P, "medications", "Medication record", "2026-01-01", D)
    records = [
        {"id": 0, "hash": digest, "ref": "record-0", "added_by": D, "timestamp": 10},
        {"id": 1, "hash": "cd" * 32, "ref": "record-1", "added_by": D, "timestamp": 11},
    ]
    monkeypatch.setattr("app.main.chain.can_access", lambda *args: True)
    monkeypatch.setattr("app.main.chain.get_records", lambda *args: records)
    monkeypatch.setattr("app.main.storage.get", lambda ref: blob)
    writes = []
    monkeypatch.setattr("app.main.chain.log_access", lambda *args: writes.append(args) or "0xaudit")

    response = client.get(f"/records/{P}/0")
    assert response.status_code == 200 and response.json()["content"] == "Penicillin allergy."
    assert client.get(f"/records/{P}/1").status_code == 404
    assert writes[0][2:] == (0, "RECORD_VIEWED")
    as_user(P, "patient")
    assert "record_access" in {item["kind"] for item in client.get("/notifications").json()}


def test_owner_can_review_and_export_decrypted_records(client, monkeypatch):
    as_user(P, "patient")
    blob, digest = crypto.encrypt(b"Owner's own note.", P)
    workflow.save_record_metadata(digest, P, "visit_notes", "Personal note", "2026-03-01", P)
    record = {"id": 0, "hash": digest, "ref": "owner-record", "added_by": P, "timestamp": 20}
    monkeypatch.setattr("app.main.chain.get_own_records", lambda address: [record])
    monkeypatch.setattr("app.main.storage.get", lambda ref: blob)

    reviewed = client.get("/owner/records")
    assert reviewed.status_code == 200
    assert reviewed.json()[0]["content"] == "Owner's own note."
    assert "ref" not in reviewed.json()[0]
    export = client.get("/owner/export")
    assert export.status_code == 200
    assert export.json()["records"][0]["title"] == "Personal note"


def test_owner_records_continue_after_missing_encrypted_file(client, monkeypatch):
    as_user(P, "patient")

    valid_blob, valid_digest = crypto.encrypt(
        b"Synthetic follow-up note.",
        P,
    )

    missing_record = {
        "id": 0,
        "hash": "ab" * 32,
        "ref": "missing-owner-record",
        "added_by": P,
        "timestamp": 20,
    }
    valid_record = {
        "id": 1,
        "hash": valid_digest,
        "ref": "valid-owner-record",
        "added_by": P,
        "timestamp": 21,
    }

    monkeypatch.setattr(
        "app.main.chain.get_own_records",
        lambda address: [missing_record, valid_record],
    )

    def get_object(ref):
        if ref == "missing-owner-record":
            from app.storage import StorageObjectNotFound
            raise StorageObjectNotFound("Missing test object")
        if ref == "valid-owner-record":
            return valid_blob
        raise AssertionError(f"Unexpected storage reference: {ref}")

    monkeypatch.setattr("app.main.storage.get", get_object)

    response = client.get("/owner/records")

    assert response.status_code == 200
    records = response.json()
    assert len(records) == 2

    assert records[0]["id"] == 0
    assert records[0]["available"] is False
    assert records[0]["content"] == ""
    assert records[0]["availability_issue"] == (
        "Encrypted file unavailable in storage"
    )

    assert records[1]["id"] == 1
    assert records[1]["available"] is True
    assert records[1]["content"] == "Synthetic follow-up note."
    assert records[1]["availability_issue"] is None


def test_owner_can_flag_record_and_author_can_review_flag(client, monkeypatch):
    approve_scope(P, D, categories=("allergies",))
    blob, digest = crypto.encrypt(b"Allergy note.", P)
    workflow.save_record_metadata(digest, P, "allergies", "Allergy note", "2026-01-01", D)
    record = {"id": 0, "hash": digest, "ref": "record-0", "added_by": D, "timestamp": 20}
    monkeypatch.setattr("app.main.chain.get_own_records", lambda address: [record])
    monkeypatch.setattr("app.main.chain.get_records", lambda *args: [record])
    monkeypatch.setattr("app.main.chain.can_access", lambda *args: True)

    as_user(P, "patient")
    flagged = client.post(f"/records/{P}/0/flags", json={"reason": "The visit date is incorrect."})
    assert flagged.status_code == 200
    as_user(D, "clinician")
    flags = client.get(f"/records/{P}/0/flags")
    assert flags.status_code == 200 and flags.json()[0]["reason"] == "The visit date is incorrect."


def test_unreachable_model_is_503_not_500(client, monkeypatch):
    as_user(D, "clinician")
    approve_scope(P, D)
    monkeypatch.setattr("app.main.chain.can_access", lambda *args: True)
    monkeypatch.setattr("app.main.chain.get_records", lambda *args: [])

    async def boom(*a, **k):
        raise httpx.ConnectError("ollama down")

    monkeypatch.setattr("app.main.agents.run_summary", boom)
    r = client.post("/agent/summary", json={"patient": P})
    assert r.status_code == 503 and "Ollama" in r.json()["detail"]


def test_summary_uses_only_authorized_records_and_returns_audit_status(
    client, monkeypatch
):
    as_user(D, "clinician")
    approve_scope(P, D, categories=("allergies",))

    monkeypatch.setattr(
        "app.main.chain.can_access",
        lambda *args: True,
    )

    records = [
        {
            "id": 0,
            "hash": "ab" * 32,
            "ref": "allergy-record",
            "added_by": D,
            "timestamp": 10,
        },
        {
            "id": 1,
            "hash": "cd" * 32,
            "ref": "medication-record",
            "added_by": D,
            "timestamp": 11,
        },
    ]

    monkeypatch.setattr(
        "app.main.chain.get_records",
        lambda *args: records,
    )

    workflow.save_record_metadata(
        "ab" * 32, P, "allergies", "Allergy record", "2026-01-01", D
    )
    workflow.save_record_metadata(
        "cd" * 32, P, "medications", "Medication record", "2026-01-01", D
    )

    captured = {}

    async def fake_summary(
        provider, patient, question, topic, allowed_record_ids=None
    ):
        captured["provider"] = provider
        captured["patient"] = patient
        captured["allowed_record_ids"] = allowed_record_ids

        return {
            "summary": "Synthetic allergy summary.",
            "key_points": ["Penicillin allergy"],
            "record_ids": [0],
            "audit_tx": [
                {
                    "event_id": "test-event-1",
                    "status": "failed",
                    "tx_hash": None,
                }
            ],
            "trace": ["Synthetic test trace"],
        }

    monkeypatch.setattr(
        "app.main.agents.run_summary",
        fake_summary,
    )
    monkeypatch.setattr(
        workflow,
        "notify_record_access",
        lambda *args: None,
    )

    response = client.post(
        "/agent/summary",
        json={
            "patient": P,
            "question": "Summarize relevant allergies.",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert captured["provider"] == D.lower()
    assert captured["patient"] == P
    assert captured["allowed_record_ids"] == {0}

    assert body["summary"] == "Synthetic allergy summary."
    assert body["record_ids"] == [0]
    assert body["audit_tx"][0]["event_id"] == "test-event-1"
    assert body["audit_tx"][0]["status"] == "failed"


def test_patient_can_upload_and_download_pdf_attachment(client, monkeypatch):
    from app import record_payload

    as_user(P, "patient")
    stored = {}
    monkeypatch.setattr(
        "app.main.storage.put",
        lambda blob: stored.setdefault("blob", blob) and "ehr/pdf-record",
    )

    pdf = b"%PDF-1.4\n% synthetic test PDF\n%%EOF"
    response = client.post(
        "/records/encrypt-with-attachment",
        data={
            "patient": P,
            "content": "Synthetic consultation note.",
            "title": "Consultation with attachment",
            "category": "visit_notes",
            "record_date": "2026-11-20",
        },
        files={"file": ("consultation.pdf", pdf, "application/pdf")},
    )

    assert response.status_code == 200, response.text
    digest = response.json()["hash"]
    decoded = record_payload.decode_record(crypto.decrypt(stored["blob"], P))
    assert decoded["content"] == "Synthetic consultation note."
    assert decoded["attachment"]["filename"] == "consultation.pdf"
    assert decoded["_attachment_bytes"] == pdf

    record = {
        "id": 0,
        "hash": digest,
        "ref": "ehr/pdf-record",
        "added_by": P,
        "timestamp": 20,
    }
    monkeypatch.setattr("app.main.chain.get_own_records", lambda address: [record])
    monkeypatch.setattr("app.main.storage.get", lambda ref: stored["blob"])

    reviewed = client.get("/owner/records")
    assert reviewed.status_code == 200
    assert reviewed.json()[0]["attachment"]["filename"] == "consultation.pdf"
    assert "_attachment_bytes" not in reviewed.text

    downloaded = client.get(f"/records/{P}/0/attachment")
    assert downloaded.status_code == 200
    assert downloaded.content == pdf
    assert downloaded.headers["content-type"] == "application/pdf"


def test_pdf_upload_rejects_non_pdf_and_oversized_files(client, monkeypatch):
    as_user(P, "patient")
    form = {
        "patient": P,
        "content": "Synthetic note.",
        "title": "Test attachment",
        "category": "visit_notes",
        "record_date": "2026-11-20",
    }

    invalid = client.post(
        "/records/encrypt-with-attachment",
        data=form,
        files={"file": ("not-a-pdf.pdf", b"not a PDF", "application/pdf")},
    )
    assert invalid.status_code == 422

    from app import record_payload
    oversized = b"%PDF-" + (b"x" * record_payload.MAX_PDF_BYTES)
    too_large = client.post(
        "/records/encrypt-with-attachment",
        data=form,
        files={"file": ("large.pdf", oversized, "application/pdf")},
    )
    assert too_large.status_code == 413


def test_clinician_pdf_download_respects_approved_categories(client, monkeypatch):
    from app import record_payload

    as_user(D, "clinician")
    approve_scope(P, D, categories=("allergies",))
    monkeypatch.setattr("app.main.chain.can_access", lambda *args: True)

    allowed_pdf = b"%PDF-1.4\n% allowed synthetic PDF\n%%EOF"
    restricted_pdf = b"%PDF-1.4\n% restricted synthetic PDF\n%%EOF"

    allowed_blob, allowed_hash = crypto.encrypt(
        record_payload.encode_record("Allergy note.", allowed_pdf, "allergy.pdf"), P,
    )
    restricted_blob, restricted_hash = crypto.encrypt(
        record_payload.encode_record("Medication note.", restricted_pdf, "medication.pdf"), P,
    )

    workflow.save_record_metadata(
        allowed_hash, P, "allergies", "Allergy record", "2026-11-20", D,
    )
    workflow.save_record_metadata(
        restricted_hash, P, "medications", "Medication record", "2026-11-20", D,
    )

    records = [
        {"id": 0, "hash": allowed_hash, "ref": "allowed", "added_by": D, "timestamp": 20},
        {"id": 1, "hash": restricted_hash, "ref": "restricted", "added_by": D, "timestamp": 21},
    ]
    blobs = {"allowed": allowed_blob, "restricted": restricted_blob}
    monkeypatch.setattr("app.main.chain.get_records", lambda *args: records)
    monkeypatch.setattr("app.main.storage.get", lambda ref: blobs[ref])

    audit = []
    monkeypatch.setattr(
        "app.main.chain.log_access",
        lambda *args: audit.append(args) or "0xaudit",
    )

    allowed = client.get(f"/records/{P}/0/attachment")
    assert allowed.status_code == 200
    assert allowed.content == allowed_pdf
    assert audit[-1][2:] == (0, "ATTACHMENT_DOWNLOADED")

    restricted = client.get(f"/records/{P}/1/attachment")
    assert restricted.status_code == 404
