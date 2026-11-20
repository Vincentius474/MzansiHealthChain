
"""Tests for persistent audit-event workflow."""

from app import workflow
import pytest
from web3.exceptions import TimeExhausted

PATIENT = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
PROVIDER = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"


def test_create_audit_event_starts_pending():
    event_id = workflow.create_audit_event(
        PATIENT, PROVIDER, 7, "RECORD_VIEWED"
    )

    events = workflow.list_audit_events()

    assert len(events) == 1
    event = events[0]

    assert event["id"] == event_id
    assert event["patient"] == PATIENT.lower()
    assert event["provider"] == PROVIDER.lower()
    assert event["record_id"] == 7
    assert event["action"] == "RECORD_VIEWED"
    assert event["status"] == "pending"
    assert event["tx_hash"] is None
    assert event["attempts"] == 0


def test_audit_event_can_be_marked_failed():
    event_id = workflow.create_audit_event(
        PATIENT, PROVIDER, 7, "RECORD_VIEWED"
    )

    assert workflow.mark_audit_failed(event_id, "RPC unavailable")

    event = workflow.list_audit_events()[0]

    assert event["status"] == "failed"
    assert event["last_error"] == "RPC unavailable"
    assert event["attempts"] == 1


def test_failed_event_can_later_be_confirmed():
    event_id = workflow.create_audit_event(
        PATIENT, PROVIDER, 7, "RECORD_VIEWED"
    )

    workflow.mark_audit_failed(event_id, "Temporary RPC failure")

    assert workflow.mark_audit_confirmed(event_id, "0xabc123")

    event = workflow.list_audit_events()[0]

    assert event["status"] == "confirmed"
    assert event["tx_hash"] == "0xabc123"
    assert event["last_error"] is None
    assert event["attempts"] == 2


def test_confirmed_event_cannot_be_downgraded():
    event_id = workflow.create_audit_event(
        PATIENT, PROVIDER, 7, "RECORD_VIEWED"
    )

    workflow.mark_audit_confirmed(event_id, "0xabc123")

    assert not workflow.mark_audit_failed(event_id, "Late failure")
    assert not workflow.mark_audit_confirmed(event_id, "0xdef456")

    event = workflow.list_audit_events()[0]

    assert event["status"] == "confirmed"
    assert event["tx_hash"] == "0xabc123"


def test_audit_events_can_be_filtered_by_status():
    workflow.create_audit_event(
        PATIENT, PROVIDER, 7, "RECORD_VIEWED"
    )

    failed_id = workflow.create_audit_event(
        PATIENT, PROVIDER, 8, "ATTACHMENT_DOWNLOADED"
    )
    workflow.mark_audit_failed(failed_id, "RPC unavailable")

    assert len(workflow.list_audit_events(status="pending")) == 1
    assert len(workflow.list_audit_events(status="failed")) == 1
    assert len(workflow.list_audit_events(status="confirmed")) == 0


def test_submit_audit_event_confirms_successful_transaction(monkeypatch):
    from types import SimpleNamespace
    from app import chain

    tx_hash = "0xabc123"

    monkeypatch.setattr(
        chain,
        "log_access",
        lambda *args: tx_hash,
    )
    monkeypatch.setattr(
        chain,
        "w3",
        SimpleNamespace(
            eth=SimpleNamespace(
                wait_for_transaction_receipt=lambda *args, **kwargs:
                    SimpleNamespace(status=1)
            )
        ),
    )

    result = workflow.submit_audit_event(
        PATIENT, PROVIDER, 7, "RECORD_VIEWED"
    )

    assert result["status"] == "confirmed"
    assert result["tx_hash"] == tx_hash

    event = workflow.list_audit_events()[0]
    assert event["status"] == "confirmed"
    assert event["tx_hash"] == tx_hash


def test_submit_audit_event_retains_failed_submission(monkeypatch):
    from app import chain

    def fail_submission(*args):
        raise RuntimeError("Relayer rejected")

    monkeypatch.setattr(chain, "log_access", fail_submission)

    result = workflow.submit_audit_event(
        PATIENT, PROVIDER, 7, "RECORD_VIEWED"
    )

    assert result["status"] == "failed"
    assert result["tx_hash"] is None

    event = workflow.list_audit_events()[0]
    assert event["status"] == "failed"
    assert event["last_error"] == "RuntimeError"


def test_submit_audit_event_rejects_reverted_receipt(monkeypatch):
    from types import SimpleNamespace
    from app import chain

    monkeypatch.setattr(
        chain,
        "log_access",
        lambda *args: "0xreverted",
    )
    monkeypatch.setattr(
        chain,
        "w3",
        SimpleNamespace(
            eth=SimpleNamespace(
                wait_for_transaction_receipt=lambda *args, **kwargs:
                    SimpleNamespace(status=0)
            )
        ),
    )

    result = workflow.submit_audit_event(
        PATIENT, PROVIDER, 7, "RECORD_VIEWED"
    )

    assert result["status"] == "failed"

    event = workflow.list_audit_events()[0]
    assert event["status"] == "failed"
    assert event["last_error"] == "TransactionReverted"


def test_submit_audit_event_keeps_pending_transaction_after_timeout(monkeypatch):
    from types import SimpleNamespace
    from app import chain

    tx_hash = "0xpending123"

    monkeypatch.setattr(
        chain,
        "log_access",
        lambda *args: tx_hash,
    )

    def timeout(*args, **kwargs):
        raise TimeExhausted("Transaction receipt not found")

    monkeypatch.setattr(
        chain,
        "w3",
        SimpleNamespace(
            eth=SimpleNamespace(
                wait_for_transaction_receipt=timeout
            )
        ),
    )

    result = workflow.submit_audit_event(
        PATIENT, PROVIDER, 7, "RECORD_VIEWED"
    )

    assert result["status"] == "pending"
    assert result["tx_hash"] == tx_hash

    event = workflow.list_audit_events()[0]
    assert event["status"] == "pending"
    assert event["tx_hash"] == tx_hash


def test_submit_audit_event_does_not_claim_unpersisted_confirmation(
    monkeypatch,
):
    from types import SimpleNamespace
    from app import chain

    tx_hash = "0xconfirmed123"

    monkeypatch.setattr(
        chain,
        "log_access",
        lambda *args: tx_hash,
    )

    monkeypatch.setattr(
        chain,
        "w3",
        SimpleNamespace(
            eth=SimpleNamespace(
                wait_for_transaction_receipt=lambda *args, **kwargs:
                    SimpleNamespace(status=1)
            )
        ),
    )

    monkeypatch.setattr(
        workflow,
        "mark_audit_confirmed",
        lambda event_id, submitted_hash: False,
    )

    with pytest.raises(RuntimeError, match="confirmation"):
        workflow.submit_audit_event(
            PATIENT, PROVIDER, 7, "RECORD_VIEWED"
        )

    event = workflow.list_audit_events()[0]
    assert event["status"] == "pending"
    assert event["tx_hash"] == tx_hash

def test_submit_audit_event_keeps_pending_after_receipt_rpc_error(
    monkeypatch,
):
    from types import SimpleNamespace
    from app import chain

    tx_hash = "0xuncertain123"

    monkeypatch.setattr(
        chain,
        "log_access",
        lambda *args: tx_hash,
    )

    def receipt_error(*args, **kwargs):
        raise RuntimeError("RPC temporarily unavailable")

    monkeypatch.setattr(
        chain,
        "w3",
        SimpleNamespace(
            eth=SimpleNamespace(
                wait_for_transaction_receipt=receipt_error
            )
        ),
    )

    result = workflow.submit_audit_event(
        PATIENT, PROVIDER, 7, "RECORD_VIEWED"
    )

    assert result["status"] == "pending"
    assert result["tx_hash"] == tx_hash

    event = workflow.list_audit_events()[0]
    assert event["status"] == "pending"
    assert event["tx_hash"] == tx_hash
    assert event["last_error"] == "RuntimeError"