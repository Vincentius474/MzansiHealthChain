from web3 import Web3

from .config import settings

w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
relayer = w3.eth.account.from_key(settings.relayer_private_key)

_REG = [
    {"name": "roleOf", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "", "type": "address"}], "outputs": [{"name": "", "type": "uint8"}]},
]
_CON = [
    {"name": "consentExpiry", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "patient", "type": "address"}, {"name": "provider", "type": "address"}],
     "outputs": [{"name": "", "type": "uint64"}]},
]
_ACL = [
    {"name": "canAccess", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "provider", "type": "address"}, {"name": "patient", "type": "address"}],
     "outputs": [{"name": "", "type": "bool"}]},
    {"name": "getRecords", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "provider", "type": "address"}, {"name": "patient", "type": "address"}],
     "outputs": [{"name": "", "type": "tuple[]", "components": [
         {"name": "ciphertextHash", "type": "bytes32"}, {"name": "storageRef", "type": "string"},
         {"name": "addedBy", "type": "address"}, {"name": "timestamp", "type": "uint64"}]}]},
    {"name": "getOwnRecords", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "tuple[]", "components": [
         {"name": "ciphertextHash", "type": "bytes32"}, {"name": "storageRef", "type": "string"},
         {"name": "addedBy", "type": "address"}, {"name": "timestamp", "type": "uint64"}]}]},
]
_AUDIT = [
    {"name": "logAccess", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "patient", "type": "address"}, {"name": "provider", "type": "address"},
                {"name": "recordId", "type": "uint256"}, {"name": "actionHash", "type": "bytes32"}],
     "outputs": []},
    {"type": "event", "name": "AccessLogged", "anonymous": False, "inputs": [
        {"name": "patient", "type": "address", "indexed": True},
        {"name": "provider", "type": "address", "indexed": True},
        {"name": "recordId", "type": "uint256", "indexed": True},
        {"name": "actionHash", "type": "bytes32", "indexed": False},
        {"name": "timestamp", "type": "uint64", "indexed": False}]},
]

registry = w3.eth.contract(address=Web3.to_checksum_address(settings.registry_addr), abi=_REG)
consent = w3.eth.contract(address=Web3.to_checksum_address(settings.consent_addr), abi=_CON)
access = w3.eth.contract(address=Web3.to_checksum_address(settings.access_addr), abi=_ACL)
audit = w3.eth.contract(address=Web3.to_checksum_address(settings.audit_addr), abi=_AUDIT)

ROLES = {0: "none", 1: "patient", 2: "clinician", 3: "facility"}
NO_RECORD = 2**256 - 1  # matches AuditLog.NO_RECORD


def role_of(addr: str) -> str:
    return ROLES[registry.functions.roleOf(Web3.to_checksum_address(addr)).call()]


def can_access(provider: str, patient: str) -> bool:
    return access.functions.canAccess(Web3.to_checksum_address(provider), Web3.to_checksum_address(patient)).call()


def consent_expiry(patient: str, provider: str) -> int:
    return int(consent.functions.consentExpiry(
        Web3.to_checksum_address(patient), Web3.to_checksum_address(provider),
    ).call())


def get_records(provider: str, patient: str) -> list[dict]:
    rows = access.functions.getRecords(Web3.to_checksum_address(provider), Web3.to_checksum_address(patient)).call()
    return [{"id": i, "hash": r[0].hex(), "ref": r[1], "added_by": r[2], "timestamp": r[3]} for i, r in enumerate(rows)]


def get_own_records(patient: str) -> list[dict]:
    rows = access.functions.getOwnRecords().call({"from": Web3.to_checksum_address(patient)})
    return [{"id": i, "hash": r[0].hex(), "ref": r[1], "added_by": r[2], "timestamp": r[3]} for i, r in enumerate(rows)]


def log_access(patient: str, provider: str, record_id: int, action: str) -> str:
    """Relayer can ONLY write audit entries. It has no power over consent or records."""
    tx = audit.functions.logAccess(
        Web3.to_checksum_address(patient), Web3.to_checksum_address(provider),
        record_id, Web3.keccak(text=action),
    ).build_transaction({
        "from": relayer.address, "nonce": w3.eth.get_transaction_count(relayer.address),
        "chainId": w3.eth.chain_id,
    })
    signed = relayer.sign_transaction(tx)
    return w3.eth.send_raw_transaction(signed.raw_transaction).to_0x_hex()


_ACTION_NAMES = {
    bytes(Web3.keccak(text=name)): name
    for name in ("SUMMARY_REQUESTED", "ACCESS_DENIED", "RECORD_LISTED", "RECORD_VIEWED")
}


def _format_audit_rows(logs: list[dict], limit: int) -> list[dict]:
    out = []
    for lg in reversed(logs[-limit:]):
        a = lg["args"]
        out.append({
            "patient": a["patient"],
            "provider": a["provider"],
            "record_id": None if a["recordId"] == NO_RECORD else a["recordId"],
            "action": _ACTION_NAMES.get(bytes(a["actionHash"]), "UNKNOWN"),
            "timestamp": a["timestamp"],
            "tx": lg["transactionHash"].to_0x_hex(),
        })
    return out


def _get_audit_logs(from_block: int, filters: dict) -> list[dict]:
    """Fetch audit events in batches of at most 100 blocks."""
    latest_block = w3.eth.block_number
    logs = []

    start = from_block

    while start <= latest_block:
        end = min(start + 99, latest_block)

        batch = audit.events.AccessLogged().get_logs(
            from_block=start,
            to_block=end,
            argument_filters=filters,
        )

        logs.extend(batch)
        start = end + 1

    return logs


def audit_trail(patient: str, limit: int = 100) -> list[dict]:
    """Newest-first access events for one patient, read from AuditLog events."""
    logs = _get_audit_logs(
        settings.audit_from_block,
        {"patient": Web3.to_checksum_address(patient)},
    )
    return _format_audit_rows(logs, limit)


def provider_audit_trail(provider: str, limit: int = 100) -> list[dict]:
    """Newest-first actions performed by one provider."""
    logs = _get_audit_logs(
        settings.audit_from_block,
        {"provider": Web3.to_checksum_address(provider)},
    )
    return _format_audit_rows(logs, limit)