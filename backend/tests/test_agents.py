"""Pipeline logic with the chain, storage and LLM mocked out."""
import pytest

from app import agents, crypto

P = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
D = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"


class FakeStorage:
    def __init__(self): self.blobs = {}
    def put(self, b): ref = f"r{len(self.blobs)}"; self.blobs[ref] = b; return ref
    def get(self, ref): return self.blobs[ref]


@pytest.fixture
def world(monkeypatch):
    store = FakeStorage()
    blob, digest = crypto.encrypt(b"Allergic to penicillin.", P)
    ref = store.put(blob)
    state = {"allowed": True, "logs": [],
             "records": [{"id": 0, "hash": digest, "ref": ref, "added_by": D, "timestamp": 1}]}
    monkeypatch.setattr(agents, "storage", store)
    monkeypatch.setattr(agents.chain, "can_access", lambda prov, pat: state["allowed"])
    monkeypatch.setattr(agents.chain, "get_records", lambda prov, pat: state["records"])
    monkeypatch.setattr(agents.chain, "log_access",
                        lambda pat, prov, rid, act: state["logs"].append((rid, act)) or "0xabc")

    async def fake_complete(prompt, *, sensitive, complexity="simple"):
        assert sensitive is True, "decrypted data must never leave the local model"
        assert "penicillin" in prompt
        assert "out-of-scope record" not in prompt
        return '{"summary": "Penicillin allergy.", "key_points": ["allergy"], "record_ids": [0]}', "ollama"

    monkeypatch.setattr(agents.llm, "complete", fake_complete)
    return state, store


async def test_happy_path_audits_the_read(world):
    state, _ = world
    out = await agents.run_summary(D, P, "history?")
    assert out["summary"] == "Penicillin allergy."
    assert state["logs"] == [(0, "SUMMARY_REQUESTED")]


async def test_denied_path_logs_attempt_and_never_decrypts(world, monkeypatch):
    state, _ = world
    state["allowed"] = False
    monkeypatch.setattr(agents.crypto, "decrypt", lambda *a: pytest.fail("decrypted without consent"))
    with pytest.raises(agents.AccessDenied):
        await agents.run_summary(D, P, "history?")
    assert state["logs"] == [(agents.chain.NO_RECORD, "ACCESS_DENIED")]


async def test_audit_failure_does_not_mask_denial(world, monkeypatch):
    state, _ = world
    state["allowed"] = False

    def boom(*a): raise RuntimeError("rpc down")
    monkeypatch.setattr(agents.chain, "log_access", boom)
    with pytest.raises(agents.AccessDenied):
        await agents.run_summary(D, P, "history?")


async def test_tampered_record_is_skipped(world):
    state, store = world
    ref = state["records"][0]["ref"]
    store.blobs[ref] = store.blobs[ref][:-1] + b"\x00"  # hash no longer matches on-chain value
    out = await agents.run_summary(D, P, "history?")
    assert out["summary"] == "No verified records available."
    assert state["logs"] == []


async def test_summary_never_decrypts_records_outside_approved_scope(world):
    state, store = world
    blob, digest = crypto.encrypt(b"out-of-scope record", P)
    state["records"].append({
        "id": 1,
        "hash": digest,
        "ref": store.put(blob),
        "added_by": D,
        "timestamp": 2,
    })

    out = await agents.run_summary(D, P, "history?", allowed_record_ids={0})

    assert out["summary"] == "Penicillin allergy."
    assert state["logs"] == [(0, "SUMMARY_REQUESTED")]
