export type Session = {
  token: string;
  email: string | null;
  address: string | null;
  role: "patient" | "clinician" | "facility";
};
const KEY = "MzansiHealthChain.session";

export function saveSession(token: string) {
  const claims = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
  const s: Session = {
    token,
    email: claims.email ?? null,
    address: claims.wallet ?? (claims.auth_method === "wallet" ? claims.sub : null),
    role: claims.role,
  };
  sessionStorage.setItem(KEY, JSON.stringify(s));
  return s;
}
export function getSession(): Session | null {
  const raw = typeof window === "undefined" ? null : sessionStorage.getItem(KEY);
  return raw ? JSON.parse(raw) : null;
}
export function clearSession() { sessionStorage.removeItem(KEY); }
