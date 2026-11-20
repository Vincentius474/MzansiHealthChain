
import base64
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from . import crypto
from .config import settings

from web3.exceptions import TimeExhausted

DB_PATH = Path(settings.data_dir) / "workflow.sqlite3"

CATEGORIES = (
    "allergies",
    "diagnoses",
    "imaging",
    "lab_results",
    "medications",
    "visit_notes",
    "other",
)


def _execute(db: Any, sql: str, params: tuple = ()):
    """Execute SQL using the placeholder style required by the database."""
    if isinstance(db, sqlite3.Connection):
        return db.execute(sql, params)

    return db.execute(sql.replace("?", "%s"), params)


def _connect():
    """Connect to Neon PostgreSQL or the local/test SQLite database."""
    if settings.database_url:
        import psycopg
        from psycopg.rows import dict_row

        db = psycopg.connect(
            settings.database_url,
            row_factory=dict_row,
            connect_timeout=10,
        )

        schema = (
            """
            CREATE TABLE IF NOT EXISTS access_requests (
                id TEXT PRIMARY KEY,
                patient TEXT NOT NULL,
                requester TEXT NOT NULL,
                purpose TEXT NOT NULL,
                categories TEXT NOT NULL,
                duration_days INTEGER NOT NULL,
                urgent BOOLEAN NOT NULL,
                status TEXT NOT NULL,
                approved_categories TEXT,
                expires_at BIGINT,
                created_at BIGINT NOT NULL,
                decided_at BIGINT
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS access_requests_patient
            ON access_requests(patient, created_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS access_requests_requester
            ON access_requests(requester, created_at)
            """,
            """
            CREATE TABLE IF NOT EXISTS record_metadata (
                hash TEXT PRIMARY KEY,
                patient TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                record_date TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at BIGINT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                recipient TEXT NOT NULL,
                kind TEXT NOT NULL,
                message TEXT NOT NULL,
                request_id TEXT,
                record_id BIGINT,
                created_at BIGINT NOT NULL,
                read_at BIGINT
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS notifications_recipient
            ON notifications(recipient, created_at)
            """,
            """
            CREATE TABLE IF NOT EXISTS record_flags (
                id TEXT PRIMARY KEY,
                patient TEXT NOT NULL,
                record_id BIGINT NOT NULL,
                owner TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at BIGINT NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS record_flags_record
            ON record_flags(patient, record_id, created_at)
            """,
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                patient TEXT NOT NULL,
                provider TEXT NOT NULL,
                record_id BIGINT,
                action TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                tx_hash TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS audit_events_status_created
            ON audit_events(status, created_at)
            """,
        )

        try:
            for statement in schema:
                db.execute(statement)
        except Exception:
            db.rollback()
            db.close()
            raise

        return db

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")

    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS access_requests (
            id TEXT PRIMARY KEY,
            patient TEXT NOT NULL,
            requester TEXT NOT NULL,
            purpose TEXT NOT NULL,
            categories TEXT NOT NULL,
            duration_days INTEGER NOT NULL,
            urgent INTEGER NOT NULL,
            status TEXT NOT NULL,
            approved_categories TEXT,
            expires_at INTEGER,
            created_at INTEGER NOT NULL,
            decided_at INTEGER
        );

        CREATE INDEX IF NOT EXISTS access_requests_patient
        ON access_requests(patient, created_at);

        CREATE INDEX IF NOT EXISTS access_requests_requester
        ON access_requests(requester, created_at);

        CREATE TABLE IF NOT EXISTS record_metadata (
            hash TEXT PRIMARY KEY,
            patient TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            record_date TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            recipient TEXT NOT NULL,
            kind TEXT NOT NULL,
            message TEXT NOT NULL,
            request_id TEXT,
            record_id INTEGER,
            created_at INTEGER NOT NULL,
            read_at INTEGER
        );

        CREATE INDEX IF NOT EXISTS notifications_recipient
        ON notifications(recipient, created_at);

        CREATE TABLE IF NOT EXISTS record_flags (
            id TEXT PRIMARY KEY,
            patient TEXT NOT NULL,
            record_id INTEGER NOT NULL,
            owner TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS record_flags_record
        ON record_flags(patient, record_id, created_at);
        CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY,
            patient TEXT NOT NULL,
            provider TEXT NOT NULL,
            record_id INTEGER,
            action TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            tx_hash TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS audit_events_status_created
        ON audit_events(status, created_at);
        """
    )

    return db


def create_request(
    patient: str,
    requester: str,
    purpose: str,
    categories: list[str],
    duration_days: int,
    urgent: bool,
) -> dict[str, Any]:
    request_id = uuid.uuid4().hex
    created_at = int(time.time())

    with _connect() as db:
        _execute(
            db,
            """INSERT INTO access_requests
               (id, patient, requester, purpose, categories, duration_days,
                urgent, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (
                request_id,
                patient.lower(),
                requester.lower(),
                _seal(purpose, patient),
                json.dumps(categories),
                duration_days,
                bool(urgent),
                created_at,
            ),
        )

        _notify(
            db,
            patient.lower(),
            "access_request",
            f"{'Urgent: ' if urgent else ''}A clinician requested access to selected records.",
            request_id,
            None,
            created_at,
        )

        row = _execute(
            db,
            "SELECT * FROM access_requests WHERE id = ?",
            (request_id,),
        ).fetchone()

    return _request(row)


def get_request(request_id: str) -> dict[str, Any] | None:
    with _connect() as db:
        row = _execute(
            db,
            "SELECT * FROM access_requests WHERE id = ?",
            (request_id,),
        ).fetchone()

    return _request(row) if row else None


def list_requests(
    *,
    patient: str | None = None,
    requester: str | None = None,
) -> list[dict[str, Any]]:
    if (patient is None) == (requester is None):
        raise ValueError("specify exactly one request owner")

    column, value = (
        ("patient", patient)
        if patient is not None
        else ("requester", requester)
    )

    with _connect() as db:
        rows = _execute(
            db,
            f"SELECT * FROM access_requests WHERE {column} = ? ORDER BY created_at DESC",
            (value.lower(),),
        ).fetchall()

    return [_request(row) for row in rows]


def approve_request(
    request_id: str,
    categories: list[str],
    expires_at: int,
) -> dict[str, Any] | None:
    now = int(time.time())

    with _connect() as db:
        if isinstance(db, sqlite3.Connection):
            db.execute("BEGIN IMMEDIATE")
            lock_clause = ""
        else:
            lock_clause = " FOR UPDATE"

        row = _execute(
            db,
            "SELECT * FROM access_requests WHERE id = ?" + lock_clause,
            (request_id,),
        ).fetchone()

        if not row or row["status"] != "pending":
            return None

        _execute(
            db,
            """UPDATE access_requests
               SET status = 'approved',
                   approved_categories = ?,
                   expires_at = ?,
                   decided_at = ?
               WHERE id = ?""",
            (json.dumps(categories), expires_at, now, request_id),
        )

        _notify(
            db,
            row["requester"],
            "access_approved",
            "Your access request was approved for the selected records and duration.",
            request_id,
            None,
            now,
        )

        updated = _execute(
            db,
            "SELECT * FROM access_requests WHERE id = ?",
            (request_id,),
        ).fetchone()

    return _request(updated)


def deny_request(request_id: str) -> dict[str, Any] | None:
    now = int(time.time())

    with _connect() as db:
        if isinstance(db, sqlite3.Connection):
            db.execute("BEGIN IMMEDIATE")
            lock_clause = ""
        else:
            lock_clause = " FOR UPDATE"

        row = _execute(
            db,
            "SELECT * FROM access_requests WHERE id = ?" + lock_clause,
            (request_id,),
        ).fetchone()

        if not row or row["status"] != "pending":
            return None

        _execute(
            db,
            "UPDATE access_requests SET status = 'denied', decided_at = ? WHERE id = ?",
            (now, request_id),
        )

        _notify(
            db,
            row["requester"],
            "access_denied",
            "Your access request was declined by the data owner.",
            request_id,
            None,
            now,
        )

        updated = _execute(
            db,
            "SELECT * FROM access_requests WHERE id = ?",
            (request_id,),
        ).fetchone()

    return _request(updated)


def allowed_categories(patient: str, requester: str) -> set[str]:
    now = int(time.time())

    with _connect() as db:
        rows = _execute(
            db,
            """SELECT approved_categories FROM access_requests
               WHERE patient = ? AND requester = ?
               AND status = 'approved' AND expires_at > ?""",
            (patient.lower(), requester.lower(), now),
        ).fetchall()

    return {
        category
        for row in rows
        for category in json.loads(row["approved_categories"] or "[]")
    }


def revoke_permissions(patient: str, requester: str) -> bool:
    now = int(time.time())

    with _connect() as db:
        if isinstance(db, sqlite3.Connection):
            db.execute("BEGIN IMMEDIATE")
            lock_clause = ""
        else:
            lock_clause = " FOR UPDATE"

        rows = _execute(
            db,
            """SELECT id FROM access_requests
               WHERE patient = ? AND requester = ? AND status = 'approved'"""
            + lock_clause,
            (patient.lower(), requester.lower()),
        ).fetchall()

        _execute(
            db,
            """UPDATE access_requests
               SET status = 'revoked', decided_at = ?
               WHERE patient = ? AND requester = ? AND status = 'approved'""",
            (now, patient.lower(), requester.lower()),
        )

        if rows:
            _notify(
                db,
                requester.lower(),
                "access_revoked",
                "The data owner withdrew your record access.",
                None,
                None,
                now,
            )

    return bool(rows)


def save_record_metadata(
    digest: str,
    patient: str,
    category: str,
    title: str,
    record_date: str,
    created_by: str,
) -> None:
    with _connect() as db:
        _execute(
            db,
            """INSERT INTO record_metadata
               (hash, patient, category, title, record_date, created_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(hash) DO UPDATE SET
               patient = excluded.patient,
               category = excluded.category,
               title = excluded.title,
               record_date = excluded.record_date,
               created_by = excluded.created_by""",
            (
                digest.lower().removeprefix("0x"),
                patient.lower(),
                category,
                _seal(title, patient),
                record_date,
                created_by.lower(),
                int(time.time()),
            ),
        )


def get_record_metadata(digest: str) -> dict[str, Any] | None:
    with _connect() as db:
        row = _execute(
            db,
            "SELECT * FROM record_metadata WHERE hash = ?",
            (digest.lower().removeprefix("0x"),),
        ).fetchone()

    if not row:
        return None

    metadata = dict(row)
    metadata["title"] = _open(metadata["title"], metadata["patient"])
    return metadata


def get_record_category(digest: str) -> str | None:
    with _connect() as db:
        row = _execute(
            db,
            "SELECT category FROM record_metadata WHERE hash = ?",
            (digest.lower().removeprefix("0x"),),
        ).fetchone()

    return row["category"] if row else None


def notify_record_access(
    patient: str,
    requester: str,
    record_id: int,
) -> None:
    with _connect() as db:
        _notify(
            db,
            patient.lower(),
            "record_access",
            f"Provider {requester[:6]}…{requester[-4:]} viewed record {record_id}.",
            None,
            record_id,
            int(time.time()),
        )


def notify_denied_access(patient: str, requester: str) -> None:
    with _connect() as db:
        _notify(
            db,
            patient.lower(),
            "access_denied",
            f"Provider {requester[:6]}…{requester[-4:]} attempted to access records without approved scope.",
            None,
            None,
            int(time.time()),
        )


def notifications(recipient: str, limit: int = 100) -> list[dict[str, Any]]:
    with _connect() as db:
        rows = _execute(
            db,
            """SELECT * FROM notifications WHERE recipient = ?
               ORDER BY created_at DESC LIMIT ?""",
            (recipient.lower(), limit),
        ).fetchall()

    return [dict(row) for row in rows]


def mark_notification_read(
    recipient: str,
    notification_id: str,
) -> bool:
    with _connect() as db:
        row = _execute(
            db,
            "SELECT id FROM notifications WHERE id = ? AND recipient = ?",
            (notification_id, recipient.lower()),
        ).fetchone()

        if not row:
            return False

        _execute(
            db,
            """UPDATE notifications
               SET read_at = COALESCE(read_at, ?)
               WHERE id = ? AND recipient = ?""",
            (int(time.time()), notification_id, recipient.lower()),
        )

    return True


def create_flag(
    patient: str,
    requester: str,
    record_id: int,
    owner: str,
    reason: str,
) -> dict[str, Any]:
    flag_id = uuid.uuid4().hex
    created_at = int(time.time())

    with _connect() as db:
        _execute(
            db,
            """INSERT INTO record_flags
               (id, patient, record_id, owner, reason, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'open', ?)""",
            (
                flag_id,
                patient.lower(),
                record_id,
                owner.lower(),
                _seal(reason, patient),
                created_at,
            ),
        )

        if requester.lower() != owner.lower():
            _notify(
                db,
                requester.lower(),
                "record_flag",
                f"The data owner flagged record {record_id} for review.",
                None,
                record_id,
                created_at,
            )

        row = _execute(
            db,
            "SELECT * FROM record_flags WHERE id = ?",
            (flag_id,),
        ).fetchone()

    return _flag(row)


def list_flags(
    patient: str,
    record_id: int | None = None,
) -> list[dict[str, Any]]:
    with _connect() as db:
        if record_id is None:
            rows = _execute(
                db,
                "SELECT * FROM record_flags WHERE patient = ? ORDER BY created_at DESC",
                (patient.lower(),),
            ).fetchall()
        else:
            rows = _execute(
                db,
                """SELECT * FROM record_flags
                   WHERE patient = ? AND record_id = ?
                   ORDER BY created_at DESC""",
                (patient.lower(), record_id),
            ).fetchall()

    return [_flag(row) for row in rows]


def create_audit_event(
    patient: str,
    provider: str,
    record_id: int | None,
    action: str,
) -> str:
    """Persist an audit event before attempting an on-chain submission."""
    event_id = uuid.uuid4().hex
    now = int(time.time())

    with _connect() as db:
        _execute(
            db,
            """INSERT INTO audit_events
               (id, patient, provider, record_id, action, status,
                attempts, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?)""",
            (
                event_id,
                patient.lower(),
                provider.lower(),
                record_id,
                action,
                now,
                now,
            ),
        )

    return event_id


def mark_audit_confirmed(event_id: str, tx_hash: str) -> bool:
    """Mark an event confirmed only after a successful chain submission."""
    now = int(time.time())

    with _connect() as db:
        cursor = _execute(
            db,
            """UPDATE audit_events
               SET status = 'confirmed',
                   tx_hash = ?,
                   last_error = NULL,
                   attempts = attempts + CASE WHEN tx_hash IS NULL THEN 1 ELSE 0 END,
                   updated_at = ?
               WHERE id = ? AND status != 'confirmed'""",
            (tx_hash, now, event_id),
        )

    return cursor.rowcount == 1

def mark_audit_submitted(event_id: str, tx_hash: str) -> bool:
    """Persist the transaction hash while its receipt is pending."""
    now = int(time.time())

    with _connect() as db:
        cursor = _execute(
            db,
            """UPDATE audit_events
               SET tx_hash = ?,
                   last_error = NULL,
                   attempts = attempts + CASE WHEN tx_hash IS NULL THEN 1 ELSE 0 END,
                   updated_at = ?
               WHERE id = ? AND status = 'pending'""",
            (tx_hash, now, event_id),
        )

    return cursor.rowcount == 1

def mark_audit_failed(event_id: str, error: str) -> bool:
    """Retain a failed submission for later investigation or retry."""
    now = int(time.time())
    safe_error = str(error)[:500]

    with _connect() as db:
        cursor = _execute(
            db,
            """UPDATE audit_events
               SET status = 'failed',
                   last_error = ?,
                   attempts = attempts + CASE WHEN tx_hash IS NULL THEN 1 ELSE 0 END,
                   updated_at = ?
               WHERE id = ? AND status != 'confirmed'""",
            (safe_error, now, event_id),
        )

    return cursor.rowcount == 1


def list_audit_events(
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List audit event metadata, optionally filtered by status."""
    limit = max(1, min(limit, 500))

    with _connect() as db:
        if status is None:
            rows = _execute(
                db,
                """SELECT * FROM audit_events
                   ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        else:
            rows = _execute(
                db,
                """SELECT * FROM audit_events
                   WHERE status = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (status, limit),
            ).fetchall()

    return [dict(row) for row in rows]

def mark_audit_pending_error(event_id: str, error: str) -> bool:
    """Retain pending status when the transaction outcome is unknown."""
    now = int(time.time())

    with _connect() as db:
        cursor = _execute(
            db,
            """UPDATE audit_events
               SET last_error = ?,
                   updated_at = ?
               WHERE id = ? AND status = 'pending' AND tx_hash IS NOT NULL""",
            (str(error)[:500], now, event_id),
        )

    return cursor.rowcount == 1


def submit_audit_event(
    patient: str,
    provider: str,
    record_id: int | None,
    action: str,
) -> dict[str, Any]:
    """Persist an audit event and track its blockchain submission."""

    event_id = create_audit_event(
        patient, provider, record_id, action
    )

    from . import chain

    # Step 1: Submit the transaction.
    try:
        tx_hash = chain.log_access(
            patient,
            provider,
            record_id if record_id is not None else chain.NO_RECORD,
            action,
        )
    except Exception as error:
        # Submission failed: no transaction hash was received.
        mark_audit_failed(event_id, type(error).__name__)

        return {
            "event_id": event_id,
            "status": "failed",
            "tx_hash": None,
        }

    # Step 2: Persist the transaction hash immediately.
    if not mark_audit_submitted(event_id, tx_hash):
        raise RuntimeError(
            "Transaction was submitted, but its hash could not be persisted."
        )

    # Step 3: Wait for the transaction receipt.
    try:
        receipt = chain.w3.eth.wait_for_transaction_receipt(
            tx_hash,
            timeout=120,
        )

    except TimeExhausted:
        # Transaction outcome is not yet known.
        # Keep the event pending and preserve its hash.
        return {
            "event_id": event_id,
            "status": "pending",
            "tx_hash": tx_hash,
        }

    except Exception as error:
        # RPC/receipt lookup failed. The transaction may still have succeeded.
        # Do not incorrectly mark an uncertain transaction as failed.
        mark_audit_pending_error(
            event_id,
            type(error).__name__,
        )

        return {
            "event_id": event_id,
            "status": "pending",
            "tx_hash": tx_hash,
        }

    # Step 4: Handle a definitive transaction revert.
    if receipt.status != 1:
        mark_audit_failed(event_id, "TransactionReverted")

        return {
            "event_id": event_id,
            "status": "failed",
            "tx_hash": tx_hash,
        }

    # Step 5: Persist confirmation only after successful mining.
    if not mark_audit_confirmed(event_id, tx_hash):
        raise RuntimeError(
            "Blockchain transaction succeeded, but audit confirmation "
            "could not be persisted."
        )

    return {
        "event_id": event_id,
        "status": "confirmed",
        "tx_hash": tx_hash,
    }


def _notify(
    db: Any,
    recipient: str,
    kind: str,
    message: str,
    request_id: str | None,
    record_id: int | None,
    created_at: int,
) -> None:
    _execute(
        db,
        """INSERT INTO notifications
           (id, recipient, kind, message, request_id, record_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            uuid.uuid4().hex,
            recipient,
            kind,
            message,
            request_id,
            record_id,
            created_at,
        ),
    )


def _request(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["purpose"] = _open(data["purpose"], data["patient"])
    data["categories"] = json.loads(data["categories"])
    data["approved_categories"] = json.loads(
        data["approved_categories"] or "[]"
    )
    data["urgent"] = bool(data["urgent"])

    if (
        data["status"] == "approved"
        and data["expires_at"]
        and data["expires_at"] <= int(time.time())
    ):
        data["status"] = "expired"

    return data


def _flag(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["reason"] = _open(data["reason"], data["patient"])
    return data


def _seal(value: str, patient: str) -> str:
    blob, _ = crypto.encrypt(value.encode("utf-8"), patient)
    return base64.urlsafe_b64encode(blob).decode("ascii")


def _open(value: str, patient: str) -> str:
    blob = base64.urlsafe_b64decode(value.encode("ascii"))
    return crypto.decrypt(blob, patient).decode("utf-8")
