import { getSession } from "./session";
import type { RecordCategory } from "./workflow";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function call<T>(path: string, body: unknown, auth = true): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth) headers.Authorization = `Bearer ${getSession()?.token}`;
  const res = await fetch(BASE + path, { method: "POST", headers, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ?? `Request failed (${res.status})`);
  return data as T;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path, { headers: { Authorization: `Bearer ${getSession()?.token}` } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ?? `Request failed (${res.status})`);
  return data as T;
}

async function download(path: string): Promise<Blob> {
  const res = await fetch(BASE + path, { headers: { Authorization: `Bearer ${getSession()?.token}` } });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail ?? `Request failed (${res.status})`);
  }
  return res.blob();
}

export const api = {
  nonce: (address: string) => call<{ message: string }>("/auth/nonce", { address }, false),
  login: (address: string, signature: string) => call<{ token: string }>("/auth/login", { address, signature }, false),
  emailLogin: (email: string, password: string, role: "patient" | "clinician") =>
    call<{ token: string }>("/auth/email-login", { email, password, role }, false),
  walletLinkNonce: (address: string) => call<{ message: string }>("/auth/wallet/nonce", { address }),
  linkWallet: (address: string, signature: string) =>
    call<{ token: string }>("/auth/wallet/link", { address, signature }),
  encryptRecord: (
    patient: string,
    content: string,
    metadata: { title: string; category: RecordCategory; record_date: string },
  ) => call<{ hash: string; ref: string }>("/records/encrypt", { patient, content, ...metadata }),
  records: (patient: string) => get<RecordMeta[]>(`/records/${patient}`),
  readRecord: (patient: string, recordId: number) => get<OwnerRecord>(`/records/${patient}/${recordId}`),
  ownerRecords: () => get<OwnerRecord[]>("/owner/records"),
  exportOwnerRecords: () => download("/owner/export"),
  audit: (patient: string) => get<AuditEntry[]>(`/audit/${patient}`),
  requesterAudit: () => get<AuditEntry[]>("/requester/audit"),
  summary: (patient: string, question: string, topic?: string) =>
    call<Summary>("/agent/summary", { patient, question, topic }),
  createAccessRequest: (body: {
    patient: string;
    purpose: string;
    categories: RecordCategory[];
    duration_days: number;
    urgent: boolean;
  }) => call<AccessRequest>("/access-requests", body),
  ownerAccessRequests: () => get<AccessRequest[]>("/access-requests/inbox"),
  myAccessRequests: () => get<AccessRequest[]>("/access-requests/mine"),
  approveAccessRequest: (id: string, categories: RecordCategory[], expiry: number, chainExpiry: number) =>
    call<AccessRequest>(`/access-requests/${id}/approve`, {
      categories,
      expiry,
      chain_expiry: chainExpiry,
    }),
  denyAccessRequest: (id: string) => call<AccessRequest>(`/access-requests/${id}/deny`, {}),
  revokePermission: (provider: string) =>
    call<{ revoked: boolean }>(`/permissions/revoke?provider=${encodeURIComponent(provider)}`, {}),
  notifications: () => get<Notification[]>("/notifications"),
  markNotificationRead: (id: string) => call<{ read: boolean }>(`/notifications/${id}/read`, {}),
  flagRecord: (patient: string, recordId: number, reason: string) =>
    call<RecordFlag>(`/records/${patient}/${recordId}/flags`, { reason }),
  recordFlags: (patient: string, recordId: number) =>
    get<RecordFlag[]>(`/records/${patient}/${recordId}/flags`),
};

export type Summary = {
  summary: string;
  key_points?: string[];
  record_ids?: number[];
  external_references?: { title: string; url: string; content: string }[];
  audit_tx?: string[];
  trace: string[];
};

export type RecordMeta = {
  id: number;
  hash: string;
  patient: string;
  title: string;
  category: RecordCategory;
  record_date: string;
  added_by: string;
  timestamp: number;
};
export type OwnerRecord = RecordMeta & {
  content: string;
  available?: boolean;
  availability_issue?: string | null;
};
export type AuditEntry = {
  patient: string; provider: string; record_id: number | null; action: string; timestamp: number; tx: string;
};
export type AccessRequest = {
  id: string;
  patient: string;
  requester: string;
  purpose: string;
  categories: RecordCategory[];
  duration_days: number;
  urgent: boolean;
  status: "pending" | "approved" | "denied" | "revoked" | "expired";
  approved_categories: RecordCategory[];
  expires_at: number | null;
  created_at: number;
  decided_at: number | null;
};
export type Notification = {
  id: string;
  recipient: string;
  kind: string;
  message: string;
  request_id: string | null;
  record_id: number | null;
  created_at: number;
  read_at: number | null;
};
export type RecordFlag = {
  id: string;
  patient: string;
  record_id: number;
  owner: string;
  reason: string;
  status: string;
  created_at: number;
};
