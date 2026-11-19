import httpx
import json
import logging
import time
from datetime import date, datetime, timezone
from typing import Literal
from urllib.parse import urlsplit
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from web3 import Web3
from cryptography.exceptions import InvalidTag

from . import agents, auth, chain, crypto, workflow
from .config import settings
from .storage import storage

app = FastAPI(title="MzansiHealthChainAPI")
local_rpc_host = urlsplit(settings.rpc_url).hostname
local_demo_origin_regex = (
    r"^http://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$"
    if settings.demo_auth_enabled and local_rpc_host in ("localhost", "127.0.0.1", "::1")
    else None
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_origin_regex=local_demo_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger = logging.getLogger(__name__)


class NonceReq(BaseModel):
    address: str


class LoginReq(BaseModel):
    address: str
    signature: str


class EmailLoginReq(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)
    role: Literal["patient", "clinician"]


class WalletLinkReq(BaseModel):
    address: str
    signature: str


class WalletLinkNonceReq(BaseModel):
    address: str


class UploadReq(BaseModel):
    patient: str
    content: str = Field(min_length=1, max_length=100_000)  # record text (demo scope)
    title: str = Field(default="Clinical note", min_length=1, max_length=120)
    category: str = "visit_notes"
    record_date: date = Field(default_factory=date.today)


class SummaryReq(BaseModel):
    patient: str
    question: str = Field("Give me a concise medical history summary.", min_length=1, max_length=1000)
    topic: str | None = Field(None, max_length=200)


class AccessRequestReq(BaseModel):
    patient: str
    purpose: str = Field(min_length=10, max_length=1000)
    categories: list[str] = Field(min_length=1, max_length=len(workflow.CATEGORIES))
    duration_days: int = Field(ge=1, le=365)
    urgent: bool = False


class ApproveRequestReq(BaseModel):
    categories: list[str] = Field(min_length=1, max_length=len(workflow.CATEGORIES))
    expiry: int = Field(gt=0)
    chain_expiry: int = Field(gt=0)


class FlagReq(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


def _require_address(value: str) -> str:
    if not Web3.is_address(value):
        raise HTTPException(422, "invalid wallet address")
    return value


def _validate_categories(categories: list[str]) -> list[str]:
    if len(set(categories)) != len(categories) or not set(categories).issubset(workflow.CATEGORIES):
        raise HTTPException(422, "choose valid, non-duplicate record categories")
    return categories


def _record_metadata(record: dict, patient: str) -> dict:
    metadata = workflow.get_record_metadata(record["hash"])
    return {
        "id": record["id"],
        "hash": "0x" + record["hash"].removeprefix("0x"),
        "added_by": record["added_by"],
        "timestamp": record["timestamp"],
        "title": metadata["title"] if metadata else "Uncategorized record",
        "category": metadata["category"] if metadata else "other",
        "record_date": metadata["record_date"] if metadata else datetime.fromtimestamp(
            record["timestamp"], timezone.utc,
        ).date().isoformat(),
        "patient": patient,
    }


def _audit_denied(patient: str, provider: str) -> None:
    try:
        chain.log_access(patient, provider, chain.NO_RECORD, "ACCESS_DENIED")
    except Exception as error:
        logger.warning("Could not audit denied access for %s: %s", provider, type(error).__name__)
    try:
        workflow.notify_denied_access(patient, provider)
    except Exception as error:
        logger.warning("Could not notify owner of denied access by %s: %s", provider, type(error).__name__)


def _scoped_records(provider: str, patient: str) -> list[dict]:
    if not chain.can_access(provider, patient):
        _audit_denied(patient, provider)
        raise HTTPException(403, "The data owner has not granted active access.")
    categories = workflow.allowed_categories(patient, provider)
    if not categories:
        _audit_denied(patient, provider)
        raise HTTPException(403, "No approved record categories are available. Request access from the data owner.")
    rows = chain.get_records(provider, patient)
    return [
        row for row in rows
        if (workflow.get_record_category(row["hash"]) or "other") in categories
    ]


def _require_patient(user: dict, patient: str) -> str:
    wallet = auth.linked_wallet(user)
    _require_address(patient)
    if user["role"] != "patient" or wallet.lower() != patient.lower():
        raise HTTPException(403, "Data owners can only manage their own records and consent.")
    return wallet


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/auth/nonce")
def nonce(req: NonceReq):
    _require_address(req.address)
    return {"message": auth.issue_nonce(req.address)}


@app.post("/auth/login")
def login(req: LoginReq):
    return {"token": auth.verify_login(req.address, req.signature)}


@app.post("/auth/email-login")
def email_login(req: EmailLoginReq):
    return {"token": auth.verify_email_login(req.email, req.password, req.role)}


@app.post("/auth/wallet/nonce")
def wallet_link_nonce(req: WalletLinkNonceReq, user=Depends(auth.current_user)):
    _require_address(req.address)
    return {"message": auth.issue_wallet_link_nonce(user, req.address)}


@app.post("/auth/wallet/link")
def wallet_link(req: WalletLinkReq, user=Depends(auth.current_user)):
    _require_address(req.address)
    return {"token": auth.verify_wallet_link(user, req.address, req.signature)}


@app.post("/records/encrypt")
def encrypt_record(req: UploadReq, user=Depends(auth.current_user)):
    """Encrypt and store a record before its owner/provider anchors it on-chain."""
    wallet = auth.linked_wallet(user)
    _require_address(req.patient)
    if req.category not in workflow.CATEGORIES:
        raise HTTPException(422, "invalid record category")
    title = req.title.strip()
    if not title:
        raise HTTPException(422, "record title must not be empty")
    if user["role"] == "patient":
        if wallet.lower() != req.patient.lower():
            raise HTTPException(403, "Data owners can only upload their own records.")
    elif user["role"] in ("clinician", "facility"):
        _scoped_records(wallet, req.patient)
        if req.category not in workflow.allowed_categories(req.patient, wallet):
            _audit_denied(req.patient, wallet)
            raise HTTPException(403, "Your approved access does not include this record category.")
        if not chain.can_access(wallet, req.patient):
            raise HTTPException(403, "The data owner's on-chain consent is not active.")
    else:
        raise HTTPException(403, "This account cannot upload records.")
    blob, digest = crypto.encrypt(req.content.encode(), req.patient)
    ref = storage.put(blob)
    workflow.save_record_metadata(
        digest, req.patient, req.category, title, req.record_date.isoformat(), wallet,
    )
    return {"hash": "0x" + digest, "ref": ref}


@app.post("/agent/summary")
async def summary(req: SummaryReq, user=Depends(auth.current_user)):
    if user["role"] not in ("clinician", "facility"):
        raise HTTPException(403, "providers only")
    wallet = auth.linked_wallet(user)
    _require_address(req.patient)
    rows = _scoped_records(wallet, req.patient)
    try:
        result = await agents.run_summary(
            wallet,
            req.patient,
            req.question,
            req.topic,
            allowed_record_ids={row["id"] for row in rows},
        )
        for row in rows:
            workflow.notify_record_access(req.patient, wallet, row["id"])
        return result
    except agents.AccessDenied as e:
        raise HTTPException(403, str(e))
    except httpx.HTTPError:
        raise HTTPException(503, "The AI model isn't reachable. Start Ollama and check OLLAMA_URL and OLLAMA_MODEL.")


@app.get("/auth/me")
def me(user=Depends(auth.current_user)):
    return {
        "email": user.get("email"),
        "address": user.get("wallet"),
        "role": user["role"],
        "wallet_linked": bool(user.get("wallet")),
    }


@app.post("/access-requests")
def create_access_request(req: AccessRequestReq, user=Depends(auth.current_user)):
    if user["role"] not in ("clinician", "facility"):
        raise HTTPException(403, "Only providers can request patient access.")
    requester = auth.linked_wallet(user)
    _require_address(req.patient)
    categories = _validate_categories(req.categories)
    purpose = req.purpose.strip()
    if len(purpose) < 10:
        raise HTTPException(422, "care purpose must be at least 10 characters")
    if chain.role_of(req.patient) != "patient":
        raise HTTPException(404, "No data owner is registered for that wallet.")
    return workflow.create_request(
        req.patient,
        requester,
        purpose,
        categories,
        req.duration_days,
        req.urgent,
    )


@app.get("/access-requests/inbox")
def access_request_inbox(user=Depends(auth.current_user)):
    wallet = auth.linked_wallet(user)
    if user["role"] != "patient":
        raise HTTPException(403, "Only data owners can review access requests.")
    return workflow.list_requests(patient=wallet)


@app.get("/access-requests/mine")
def my_access_requests(user=Depends(auth.current_user)):
    wallet = auth.linked_wallet(user)
    if user["role"] not in ("clinician", "facility"):
        raise HTTPException(403, "Only providers can view their access requests.")
    return workflow.list_requests(requester=wallet)


@app.post("/access-requests/{request_id}/approve")
def approve_access_request(request_id: str, req: ApproveRequestReq, user=Depends(auth.current_user)):
    wallet = auth.linked_wallet(user)
    if user["role"] != "patient":
        raise HTTPException(403, "Only data owners can approve access requests.")
    request = workflow.get_request(request_id)
    if not request or request["patient"] != wallet.lower():
        raise HTTPException(404, "Access request not found.")
    if request["status"] != "pending":
        raise HTTPException(409, "This access request has already been decided.")
    categories = _validate_categories(req.categories)
    if not set(categories).issubset(request["categories"]):
        raise HTTPException(422, "You can only approve categories included in the request.")
    now = int(time.time())
    if req.expiry <= now or req.expiry > now + request["duration_days"] * 86400 + 120:
        raise HTTPException(422, "Approval expiry must be within the requested duration.")
    if req.chain_expiry < req.expiry or req.chain_expiry > now + 365 * 86400 + 120:
        raise HTTPException(422, "On-chain consent must cover the approved period and stay within 365 days.")
    if chain.consent_expiry(wallet, request["requester"]) != req.chain_expiry:
        raise HTTPException(409, "Confirm the matching consent transaction in your wallet first.")
    approved = workflow.approve_request(request_id, categories, req.expiry)
    if not approved:
        raise HTTPException(409, "This access request has already been decided.")
    return approved


@app.post("/access-requests/{request_id}/deny")
def deny_access_request(request_id: str, user=Depends(auth.current_user)):
    wallet = auth.linked_wallet(user)
    if user["role"] != "patient":
        raise HTTPException(403, "Only data owners can deny access requests.")
    request = workflow.get_request(request_id)
    if not request or request["patient"] != wallet.lower():
        raise HTTPException(404, "Access request not found.")
    denied = workflow.deny_request(request_id)
    if not denied:
        raise HTTPException(409, "This access request has already been decided.")
    return denied


@app.post("/permissions/revoke")
def revoke_permission(provider: str, user=Depends(auth.current_user)):
    wallet = auth.linked_wallet(user)
    _require_patient(user, wallet)
    _require_address(provider)
    if chain.consent_expiry(wallet, provider) != 0:
        raise HTTPException(409, "Confirm the consent revocation in your wallet first.")
    workflow.revoke_permissions(wallet, provider)
    return {"revoked": True}


@app.get("/owner/records")
def owner_records(user=Depends(auth.current_user)):
    wallet = auth.linked_wallet(user)
    _require_patient(user, wallet)
    result = []
    for row in chain.get_own_records(wallet):
        metadata = _record_metadata(row, wallet)
        blob = storage.get(row["ref"])
        if crypto.sha256_hex(blob) != row["hash"].removeprefix("0x"):
            raise HTTPException(500, f"Record {row['id']} failed its integrity check.")
        try:
            content = crypto.decrypt(blob, wallet).decode("utf-8")
        except (InvalidTag, ValueError, UnicodeDecodeError):
            raise HTTPException(500, f"Record {row['id']} could not be decrypted.")
        result.append({**metadata, "content": content})
    return result


@app.get("/owner/export")
def export_owner_records(user=Depends(auth.current_user)):
    records = owner_records(user)
    content = json.dumps({"exported_at": datetime.now(timezone.utc).isoformat(), "records": records}, indent=2)
    return Response(
        content,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="health-records-export.json"'},
    )


@app.get("/records/{patient}")
def list_records(patient: str, user=Depends(auth.current_user)):
    if user["role"] not in ("clinician", "facility"):
        raise HTTPException(403, "providers only")
    wallet = auth.linked_wallet(user)
    _require_address(patient)
    rows = _scoped_records(wallet, patient)
    records = [_record_metadata(row, patient) for row in rows]
    for row in rows:
        chain.log_access(patient, wallet, row["id"], "RECORD_LISTED")
    return records


@app.get("/records/{patient}/{record_id}")
def read_record(patient: str, record_id: int, user=Depends(auth.current_user)):
    if user["role"] not in ("clinician", "facility"):
        raise HTTPException(403, "providers only")
    wallet = auth.linked_wallet(user)
    _require_address(patient)
    rows = _scoped_records(wallet, patient)
    record = next((row for row in rows if row["id"] == record_id), None)
    if not record:
        _audit_denied(patient, wallet)
        raise HTTPException(404, "Record not found in your approved categories.")
    blob = storage.get(record["ref"])
    if crypto.sha256_hex(blob) != record["hash"].removeprefix("0x"):
        raise HTTPException(500, "Record failed its integrity check.")
    try:
        content = crypto.decrypt(blob, patient).decode("utf-8")
    except (InvalidTag, ValueError, UnicodeDecodeError):
        raise HTTPException(500, "Record could not be decrypted.")
    chain.log_access(patient, wallet, record_id, "RECORD_VIEWED")
    workflow.notify_record_access(patient, wallet, record_id)
    return {**_record_metadata(record, patient), "content": content}


@app.post("/records/{patient}/{record_id}/flags")
def flag_record(patient: str, record_id: int, req: FlagReq, user=Depends(auth.current_user)):
    wallet = _require_patient(user, patient)
    rows = chain.get_own_records(wallet)
    record = next((row for row in rows if row["id"] == record_id), None)
    if not record:
        raise HTTPException(404, "Record not found.")
    flag = workflow.create_flag(
        patient, record["added_by"], record_id, wallet, req.reason.strip(),
    )
    return flag


@app.get("/records/{patient}/{record_id}/flags")
def record_flags(patient: str, record_id: int, user=Depends(auth.current_user)):
    if user["role"] not in ("clinician", "facility"):
        raise HTTPException(403, "providers only")
    wallet = auth.linked_wallet(user)
    _require_address(patient)
    rows = _scoped_records(wallet, patient)
    if not any(row["id"] == record_id for row in rows):
        _audit_denied(patient, wallet)
        raise HTTPException(404, "Record not found in your approved categories.")
    return workflow.list_flags(patient, record_id)


@app.get("/notifications")
def get_notifications(user=Depends(auth.current_user)):
    wallet = auth.linked_wallet(user)
    return workflow.notifications(wallet)


@app.post("/notifications/{notification_id}/read")
def read_notification(notification_id: str, user=Depends(auth.current_user)):
    wallet = auth.linked_wallet(user)
    if not workflow.mark_notification_read(wallet, notification_id):
        raise HTTPException(404, "Notification not found.")
    return {"read": True}


@app.get("/audit/{patient}")
def audit_trail(patient: str, user=Depends(auth.current_user)):
    """A patient can read who accessed their records. Nobody else can read it here."""
    wallet = auth.linked_wallet(user)
    _require_address(patient)
    if user["role"] != "patient" or wallet.lower() != patient.lower():
        raise HTTPException(403, "patients can only read their own audit trail")
    return chain.audit_trail(patient)


@app.get("/requester/audit")
def requester_audit_trail(user=Depends(auth.current_user)):
    if user["role"] not in ("clinician", "facility"):
        raise HTTPException(403, "providers only")
    wallet = auth.linked_wallet(user)
    return chain.provider_audit_trail(wallet)
