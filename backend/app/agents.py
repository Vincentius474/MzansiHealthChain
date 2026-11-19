"""Orchestrator + four capabilities. Hard rule: agents only READ. They cannot grant consent,
change permissions or send arbitrary transactions; the only write is the audit entry."""
import json
from dataclasses import dataclass, field

from . import chain, crypto, llm
from .storage import storage


class AccessDenied(Exception):
    pass


@dataclass
class Trace:
    steps: list[str] = field(default_factory=list)

    def add(self, s: str):
        self.steps.append(s)


def consent_agent(provider: str, patient: str, trace: Trace):
    ok = chain.can_access(provider, patient)  # source of truth = smart contract
    trace.add(f"ConsentAgent: on-chain access {'GRANTED' if ok else 'DENIED'}")
    if not ok:
        raise AccessDenied("Patient has not granted access (or consent expired)")


def retrieval_agent(
    provider: str,
    patient: str,
    trace: Trace,
    allowed_record_ids: set[int] | None = None,
) -> list[dict]:
    docs = []
    for rec in chain.get_records(provider, patient):
        if allowed_record_ids is not None and rec["id"] not in allowed_record_ids:
            continue
        blob = storage.get(rec["ref"])
        if crypto.sha256_hex(blob) != rec["hash"]:  # integrity check against on-chain hash
            trace.add(f"RetrievalAgent: record {rec['id']} FAILED integrity check, skipped")
            continue
        docs.append({"id": rec["id"], "text": crypto.decrypt(blob, patient).decode()})
    trace.add(f"RetrievalAgent: {len(docs)} verified record(s) decrypted in memory")
    return docs


async def analysis_agent(question: str, docs: list[dict], trace: Trace) -> dict:
    joined = "\n---\n".join(f"[Record {d['id']}]\n{d['text']}" for d in docs)
    prompt = (
        "You are a clinical documentation assistant. Using ONLY the records below, answer the "
        "clinician's question. Cite record ids. If information is missing, say so. "
        "Do not diagnose.\n\n"
        f"Question: {question}\n\nRecords:\n{joined}\n\n"
        'Reply as JSON: {"summary": str, "key_points": [str], "record_ids": [int]}'
    )
    # Decrypted patient data => sensitive => local Ollama only.
    text, model = await llm.complete(prompt, sensitive=True)
    trace.add(f"AnalysisAgent: summarised with {model} (patient data stayed local)")
    try:
        return json.loads(text[text.index("{"): text.rindex("}") + 1])
    except ValueError:
        return {"summary": text, "key_points": [], "record_ids": [d["id"] for d in docs]}


async def external_info_agent(topic: str, trace: Trace) -> list[dict]:
    """Optional. Query contains a medical topic only, never patient data."""
    results = await llm.tavily_search(topic)
    trace.add(f"ExternalInfo: {len(results)} Tavily result(s) for topic query")
    return results


def audit_agent(patient: str, provider: str, record_ids: list[int], action: str, trace: Trace) -> list[str]:
    hashes = [chain.log_access(patient, provider, rid, action) for rid in (record_ids or [0])]
    trace.add(f"AuditAgent: {len(hashes)} audit event(s) written to Avalanche")
    return hashes


def audit_denied(patient: str, provider: str, trace: Trace):
    """Denied attempts are audited too. A logging failure must not change the 403."""
    try:
        chain.log_access(patient, provider, chain.NO_RECORD, "ACCESS_DENIED")
        trace.add("AuditAgent: denied attempt written to Avalanche")
    except Exception as e:  # noqa: BLE001
        trace.add(f"AuditAgent: could not log denied attempt ({type(e).__name__})")


async def run_summary(
    provider: str,
    patient: str,
    question: str,
    topic: str | None = None,
    allowed_record_ids: set[int] | None = None,
) -> dict:
    trace = Trace()
    try:
        consent_agent(provider, patient, trace)
    except AccessDenied:
        audit_denied(patient, provider, trace)
        raise
    docs = retrieval_agent(provider, patient, trace, allowed_record_ids)
    if not docs:
        return {"summary": "No verified records available.", "trace": trace.steps}
    result = await analysis_agent(question, docs, trace)
    external = await external_info_agent(topic, trace) if topic else []
    tx = audit_agent(patient, provider, [d["id"] for d in docs], "SUMMARY_REQUESTED", trace)
    return {**result, "external_references": external, "audit_tx": tx, "trace": trace.steps}
