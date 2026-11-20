"""Test env: valid-looking settings so app modules import without a real chain or .env."""
import os

import pytest

# Anvil's public dev addresses (valid checksummed addresses; no funds, no secrets)
_ADDR = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
os.environ.update({
    "JWT_SECRET": "test-secret-test-secret-test-secret-123456",
    "MASTER_KEY_HEX": "11" * 32,
    "RPC_URL": "http://127.0.0.1:8545",
    "DEMO_AUTH_ENABLED": "true",
    "RELAYER_PRIVATE_KEY": "0x" + "22" * 32,
    "REGISTRY_ADDR": _ADDR, "CONSENT_ADDR": _ADDR, "ACCESS_ADDR": _ADDR, "AUDIT_ADDR": _ADDR,
})


@pytest.fixture(autouse=True)
def isolate_workflow_database(tmp_path, monkeypatch):
    from app import workflow
    monkeypatch.setattr(workflow, "DB_PATH", tmp_path / "workflow.sqlite3")
    monkeypatch.setattr(workflow.settings, "database_url", "")
