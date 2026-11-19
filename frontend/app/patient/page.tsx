"use client";
import { Contract, getAddress } from "ethers";
import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import CategoryChecklist from "@/components/CategoryChecklist";
import Shell from "@/components/Shell";
import WorkflowNotifications from "@/components/WorkflowNotifications";
import { AccessRequest, api, AuditEntry, OwnerRecord, Notification } from "@/lib/api";
import { ACCESS_ABI, ADDR, CONSENT_ABI, START_BLOCK } from "@/lib/contracts";
import { errMsg, fmtDate, short, timeLeft } from "@/lib/format";
import { useSession } from "@/lib/hooks";
import { CATEGORY_LABELS, RecordCategory } from "@/lib/workflow";

type Consent = { provider: string; expiry: number };

export default function PatientPage() {
  const { session, signer, error: walletError } = useSession(["patient"]);
  const [records, setRecords] = useState<OwnerRecord[]>([]);
  const [consents, setConsents] = useState<Consent[]>([]);
  const [trail, setTrail] = useState<AuditEntry[]>([]);
  const [requests, setRequests] = useState<AccessRequest[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [providerFilter, setProviderFilter] = useState("");
  const [dateOrder, setDateOrder] = useState<"newest" | "oldest">("newest");
  const [approvalCategories, setApprovalCategories] = useState<Record<string, RecordCategory[]>>({});
  const [approvalDays, setApprovalDays] = useState<Record<string, string>>({});
  const [flagReasons, setFlagReasons] = useState<Record<number, string>>({});
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState<RecordCategory>("visit_notes");
  const [recordDate, setRecordDate] = useState(new Date().toISOString().slice(0, 10));
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!session?.address) return;
    setError(null);
    try {
      const [nextRecords, nextTrail, nextRequests, nextNotifications] = await Promise.all([
        api.ownerRecords(),
        api.audit(session.address),
        api.ownerAccessRequests(),
        api.notifications(),
      ]);
      setRecords(nextRecords);
      setTrail(nextTrail);
      setRequests(nextRequests);
      setNotifications(nextNotifications);

      if (signer) {
        const consent = new Contract(ADDR.consent, CONSENT_ABI, signer);
        const events: any[] = await consent.queryFilter(
          consent.filters.ConsentGranted(session.address),
          START_BLOCK,
        );
        const providers = [...new Set(events.map((event) => getAddress(event.args.provider)))];
        const current: Consent[] = [];
        for (const provider of providers) {
          const expiry = Number(await consent.consentExpiry(session.address, provider));
          if (expiry > 0) current.push({ provider, expiry });
        }
        setConsents(current.sort((a, b) => b.expiry - a.expiry));
      }
    } catch (e) {
      setError(errMsg(e));
    }
  }, [session?.address, signer]);

  useEffect(() => { void load(); }, [load]);

  const refreshActivity = useCallback(async () => {
    if (!session?.address) return;
    try {
      const [nextRequests, nextNotifications] = await Promise.all([
        api.ownerAccessRequests(),
        api.notifications(),
      ]);
      setRequests(nextRequests);
      setNotifications(nextNotifications);
    } catch (e) {
      setError(errMsg(e));
    }
  }, [session?.address]);

  useEffect(() => {
    const timer = window.setInterval(() => { void refreshActivity(); }, 30_000);
    return () => window.clearInterval(timer);
  }, [refreshActivity]);

  async function run(label: string, action: () => Promise<unknown>, message: string) {
    setBusy(label);
    setError(null);
    setOk(null);
    try {
      await action();
      setOk(message);
      await load();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(null);
    }
  }

  async function submitRecord(event: FormEvent) {
    event.preventDefault();
    if (!session?.address || !signer) return setError("Connect your registered wallet in Settings first.");
    if (!title.trim() || !content.trim()) return setError("Enter a title and record content.");
    await run("upload", async () => {
      const encrypted = await api.encryptRecord(session.address!, content, {
        title: title.trim(),
        category,
        record_date: recordDate,
      });
      const access = new Contract(ADDR.access, ACCESS_ABI, signer);
      await (await access.addRecord(session.address, encrypted.hash, encrypted.ref)).wait();
      setTitle("");
      setContent("");
    }, "Your encrypted record was added to the ledger.");
  }

  async function approve(request: AccessRequest) {
    if (!session?.address || !signer) return setError("Connect your registered wallet in Settings first.");
    const owner = session.address;
    const categories = approvalCategories[request.id] ?? request.categories;
    const days = Number(approvalDays[request.id] ?? request.duration_days);
    if (!categories.length || !categories.every((item) => request.categories.includes(item))) {
      return setError("Choose at least one requested category.");
    }
    if (!Number.isInteger(days) || days < 1 || days > request.duration_days) {
      return setError(`Choose a duration between 1 and ${request.duration_days} days.`);
    }
    await run(`approve-${request.id}`, async () => {
      const consent = new Contract(ADDR.consent, CONSENT_ABI, signer);
      const expiry = Math.floor(Date.now() / 1000) + days * 86400;
      const existingExpiry = Number(await consent.consentExpiry(owner, request.requester));
      const chainExpiry = Math.max(expiry, existingExpiry);
      await (await consent.grant(request.requester, BigInt(chainExpiry))).wait();
      await api.approveAccessRequest(request.id, categories, expiry, chainExpiry);
    }, `Access approved for ${short(request.requester)}.`);
  }

  async function deny(request: AccessRequest) {
    await run(`deny-${request.id}`, () => api.denyAccessRequest(request.id), "Access request denied.");
  }

  async function revoke(consent: Consent) {
    if (!signer) return setError("Connect your registered wallet in Settings first.");
    await run(`revoke-${consent.provider}`, async () => {
      const contract = new Contract(ADDR.consent, CONSENT_ABI, signer);
      await (await contract.revoke(consent.provider)).wait();
      await api.revokePermission(consent.provider);
    }, `Access withdrawn from ${short(consent.provider)}.`);
  }

  async function flag(record: OwnerRecord) {
    const reason = flagReasons[record.id]?.trim();
    if (!reason) return setError("Describe the issue before submitting a record flag.");
    await run(`flag-${record.id}`, async () => {
      await api.flagRecord(record.patient, record.id, reason);
      setFlagReasons((current) => ({ ...current, [record.id]: "" }));
    }, "Record flagged for review.");
  }

  async function exportRecords() {
    await run("export", async () => {
      const file = await api.exportOwnerRecords();
      const url = URL.createObjectURL(file);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "health-records-export.json";
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }, "Your records export was downloaded.");
  }

  async function markRead(id: string) {
    await run(`read-${id}`, () => api.markNotificationRead(id), "Notification marked as read.");
  }

  if (!session) return null;
  if (!session.address) {
    return (
      <Shell session={session} title="Connect your wallet">
        <div className="notice">Connect your registered wallet in <Link href="/settings">Settings</Link> to manage your records and consent.</div>
      </Shell>
    );
  }

  const pendingRequests = requests.filter((request) => request.status === "pending");
  const visibleRecords = records
    .filter((record) => categoryFilter === "all" || record.category === categoryFilter)
    .filter((record) => !providerFilter || record.added_by.toLowerCase().includes(providerFilter.toLowerCase()))
    .sort((a, b) => dateOrder === "newest"
      ? b.record_date.localeCompare(a.record_date)
      : a.record_date.localeCompare(b.record_date));
  return (
    <Shell session={session} title="Data owner dashboard">
      {walletError && <div className="notice error" role="alert">{walletError}</div>}
      {error && <div className="notice error" role="alert">{error}</div>}
      {ok && <div className="notice success" role="status">{ok}</div>}

      <section>
        <div className="inline-actions">
          <h2>My health records</h2>
          <button className="secondary" disabled={busy !== null} onClick={() => void load()}>Refresh dashboard</button>
          <button className="secondary" disabled={busy !== null} onClick={exportRecords}>Download my records</button>
        </div>
        <p className="muted">Encrypted records are listed by category, provider, and record date. New entries are appended; existing records are never overwritten.</p>
        <div className="panel row">
          <label>Filter by category
            <select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
              <option value="all">All categories</option>
              <option value="allergies">Allergies</option>
              <option value="diagnoses">Diagnoses</option>
              <option value="imaging">Imaging</option>
              <option value="lab_results">Lab results</option>
              <option value="medications">Medications</option>
              <option value="visit_notes">Visit notes</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label>Filter by provider wallet
            <input value={providerFilter} onChange={(event) => setProviderFilter(event.target.value.trim())} placeholder="Address or prefix" />
          </label>
          <label>Sort by date
            <select value={dateOrder} onChange={(event) => setDateOrder(event.target.value as "newest" | "oldest")}>
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
            </select>
          </label>
        </div>
        {records.length === 0 ? <p className="muted">No records have been added yet.</p> : visibleRecords.length === 0 ? (
          <p className="muted">No records match those filters.</p>
        ) : (
          <div className="record-stack">
            {visibleRecords.map((record) => (
              <article className="panel" key={record.id}>
                <h3>{record.title}</h3>
                <p>
                  <span className="chip">{CATEGORY_LABELS[record.category]}</span>{" "}
                  · {record.record_date} · Added by <code>{short(record.added_by)}</code>
                </p>
                <details>
                  <summary>Review record</summary>
                  <pre>{record.content}</pre>
                </details>
                <label>Flag an inaccuracy or concern
                  <textarea
                    className="compact"
                    value={flagReasons[record.id] ?? ""}
                    onChange={(event) => setFlagReasons((current) => ({ ...current, [record.id]: event.target.value }))}
                    placeholder="Describe the issue for the record author."
                  />
                </label>
                <button className="secondary" disabled={busy !== null} onClick={() => flag(record)}>Submit flag</button>
              </article>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2>Add a personal record</h2>
        <form className="panel" onSubmit={submitRecord}>
          <label>Title
            <input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={120} required />
          </label>
          <div className="row">
            <label>Category
              <select value={category} onChange={(event) => setCategory(event.target.value as RecordCategory)}>
                <option value="allergies">Allergies</option>
                <option value="diagnoses">Diagnoses</option>
                <option value="imaging">Imaging</option>
                <option value="lab_results">Lab results</option>
                <option value="medications">Medications</option>
                <option value="visit_notes">Visit notes</option>
                <option value="other">Other</option>
              </select>
            </label>
            <label>Record date
              <input type="date" value={recordDate} onChange={(event) => setRecordDate(event.target.value)} required />
            </label>
          </div>
          <label>Record details
            <textarea value={content} onChange={(event) => setContent(event.target.value)} maxLength={100000} required />
            <small>Content is encrypted before storage. You’ll confirm the append-only transaction in your wallet.</small>
          </label>
          <button disabled={!signer || busy !== null}>{busy === "upload" ? "Confirm in your wallet…" : "Encrypt and add record"}</button>
        </form>
      </section>

      <section>
        <h2>Access requests</h2>
        {pendingRequests.length === 0 ? <p className="muted">No pending requests.</p> : (
          <div className="record-stack">
            {pendingRequests.map((request) => {
              const selected = approvalCategories[request.id] ?? request.categories;
              return (
                <article className="panel" key={request.id}>
                  <div className="inline-actions">
                    <h3>Request from {short(request.requester)}</h3>
                    {request.urgent && <span className="chip warn">Urgent · approval still required</span>}
                  </div>
                  <p><strong>Purpose:</strong> {request.purpose}</p>
                  <p><strong>Requested duration:</strong> up to {request.duration_days} days</p>
                  <CategoryChecklist
                    value={selected}
                    onChange={(categories) => setApprovalCategories((current) => ({ ...current, [request.id]: categories }))}
                  />
                  <label>Approve for days
                    <input
                      type="number"
                      min={1}
                      max={request.duration_days}
                      value={approvalDays[request.id] ?? String(request.duration_days)}
                      onChange={(event) => setApprovalDays((current) => ({ ...current, [request.id]: event.target.value }))}
                    />
                  </label>
                  <div className="inline-actions">
                    <button disabled={!signer || busy !== null} onClick={() => approve(request)}>
                      {busy === `approve-${request.id}` ? "Confirm in your wallet…" : "Approve selected access"}
                    </button>
                    <button className="danger" disabled={busy !== null} onClick={() => deny(request)}>
                      {busy === `deny-${request.id}` ? "Working…" : "Deny request"}
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
        {requests.some((request) => request.status !== "pending") && (
          <>
            <h3>Decision history</h3>
            <ul className="list">
              {requests.filter((request) => request.status !== "pending").map((request) => (
                <li key={request.id}>
                  <span>
                    <code>{short(request.requester)}</code> · {(request.approved_categories.length ? request.approved_categories : request.categories).map((item) => CATEGORY_LABELS[item]).join(", ")}
                    {request.expires_at ? <><br /><small>Expires {fmtDate(request.expires_at)}</small></> : null}
                  </span>
                  <span className={`chip ${request.status === "approved" ? "ok" : "bad"}`}>{request.status}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section>
        <h2>Current on-chain consents</h2>
        <p className="muted">On-chain consent is pair-level; the app limits decrypted records to the categories approved in the request history above.</p>
        {consents.length === 0 ? <p className="muted">No provider consents are recorded on-chain.</p> : (
          <ul className="list">
            {consents.map((item) => {
              const active = item.expiry > Math.floor(Date.now() / 1000);
              return (
                <li key={item.provider}>
                  <span><code>{short(item.provider)}</code> · <span className={`chip ${active ? "ok" : "warn"}`}>{timeLeft(item.expiry)}</span></span>
                  {active && <button className="danger" disabled={busy !== null} onClick={() => revoke(item)}>
                    {busy === `revoke-${item.provider}` ? "Confirm in your wallet…" : "Withdraw access"}
                  </button>}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section>
        <h2>Record access history</h2>
        {trail.length === 0 ? <p className="muted">No requester access has been logged yet.</p> : (
          <ul className="list">
          {trail.map((entry, index) => {
            const recordTitle = records.find((record) => record.id === entry.record_id)?.title;
            return (
              <li key={`${entry.tx}-${index}`}>
                <span>
                  <code>{short(entry.provider)}</code> · {fmtDate(entry.timestamp)} · {recordTitle ?? (entry.record_id === null ? "No specific record" : `Record ${entry.record_id}`)}
                </span>
                <span className={`chip ${entry.action === "ACCESS_DENIED" ? "bad" : "ok"}`}>{entry.action.replaceAll("_", " ").toLowerCase()}</span>
              </li>
            );
          })}
          </ul>
        )}
      </section>

      <WorkflowNotifications items={notifications} onRead={(id) => void markRead(id)} />
    </Shell>
  );
}
