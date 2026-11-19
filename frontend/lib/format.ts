import { id } from "ethers";

export const short = (a: string) => `${a.slice(0, 6)}…${a.slice(-4)}`;

export const fmtDate = (unixSeconds: number | bigint) =>
  new Date(Number(unixSeconds) * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

const ACTIONS: Record<string, string> = {
  [id("SUMMARY_REQUESTED")]: "Summary requested",
  [id("ACCESS_DENIED")]: "Access denied",
};
export const actionLabel = (hash: string) => ACTIONS[hash] ?? "Other access";

export function timeLeft(expiry: number): string {
  const s = expiry - Math.floor(Date.now() / 1000);
  if (s <= 0) return "expired";
  const d = Math.floor(s / 86400);
  if (d >= 1) return `${d} day${d === 1 ? "" : "s"} left`;
  const h = Math.floor(s / 3600);
  return h >= 1 ? `${h} hour${h === 1 ? "" : "s"} left` : "less than an hour left";
}

/** Pull a readable message out of ethers / wallet / fetch errors. */
export function errMsg(e: any): string {
  if (e?.code === "ACTION_REJECTED" || e?.code === 4001) return "You rejected the request in your wallet.";
  return e?.reason ?? e?.shortMessage ?? e?.message ?? "Something went wrong.";
}
