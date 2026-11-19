#!/usr/bin/env python3
"""Fill backend/.env and frontend/.env.local from a finished deployment.

Usage: python scripts/sync_env.py [chainId]     (31337 = local anvil, 43113 = Fuji, 43114 = Avalanche Mainnet)

- copies the four contract addresses and the RPC URL
- generates JWT_SECRET / MASTER_KEY_HEX if they are still placeholders (never overwrites real ones)
- on local anvil only: sets the relayer key to anvil's public dev account #2
"""
import json
import pathlib
import re
import secrets
import sys

root = pathlib.Path(__file__).resolve().parent.parent
chain_id = sys.argv[1] if len(sys.argv) > 1 else "31337"
src = root / "contracts" / "deployments" / f"{chain_id}.json"
if not src.exists():
    sys.exit(f"{src} not found. Deploy the contracts first.")
dep = json.loads(src.read_text())

RPC = {
    "31337": "http://127.0.0.1:8545",
    "43113": "https://api.avax-test.network/ext/bc/C/rpc",
    "43114": "https://api.avax.network/ext/bc/C/rpc",
}
ANVIL_RELAYER_KEY = "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"  # public dev key


def read(path: pathlib.Path, template: pathlib.Path) -> str:
    return path.read_text() if path.exists() else template.read_text()


def current(text: str, key: str) -> str | None:
    m = re.search(rf"^{key}=(.*)$", text, flags=re.M)
    return m.group(1).strip() if m else None


def put(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    if re.search(rf"^{key}=.*$", text, flags=re.M):
        return re.sub(rf"^{key}=.*$", line, text, flags=re.M)
    return text.rstrip("\n") + f"\n{line}\n"


# ---- backend/.env
be_path = root / "backend" / ".env"
be = read(be_path, root / "backend" / ".env.example")
for key, name in {"REGISTRY_ADDR": "PatientRegistry", "CONSENT_ADDR": "ConsentManagement",
                  "ACCESS_ADDR": "AccessControl", "AUDIT_ADDR": "AuditLog"}.items():
    be = put(be, key, dep[name])
if chain_id in RPC:
    be = put(be, "RPC_URL", RPC[chain_id])
be = put(be, "DEMO_AUTH_ENABLED", "true" if chain_id == "31337" else "false")
jwt = current(be, "JWT_SECRET")
if not jwt or jwt.startswith("change-me"):
    be = put(be, "JWT_SECRET", secrets.token_urlsafe(48))
mk = current(be, "MASTER_KEY_HEX")
if not mk or not re.fullmatch(r"[0-9a-fA-F]{64}", mk):
    be = put(be, "MASTER_KEY_HEX", secrets.token_hex(32))
if chain_id == "31337":
    be = put(be, "RELAYER_PRIVATE_KEY", ANVIL_RELAYER_KEY)
be_path.write_text(be)
print("updated backend/.env")

# ---- frontend/.env.local
fe_path = root / "frontend" / ".env.local"
fe = read(fe_path, root / "frontend" / ".env.local.example")
for key, name in {"NEXT_PUBLIC_REGISTRY_ADDR": "PatientRegistry", "NEXT_PUBLIC_CONSENT_ADDR": "ConsentManagement",
                  "NEXT_PUBLIC_ACCESS_ADDR": "AccessControl", "NEXT_PUBLIC_AUDIT_ADDR": "AuditLog"}.items():
    fe = put(fe, key, dep[name])
fe = put(fe, "NEXT_PUBLIC_CHAIN_ID", chain_id)
fe = put(fe, "NEXT_PUBLIC_DEMO_AUTH_ENABLED", "true" if chain_id == "31337" else "false")
if chain_id in RPC:
    fe = put(fe, "NEXT_PUBLIC_RPC_URL", RPC[chain_id])
fe_path.write_text(fe)
print("updated frontend/.env.local")
