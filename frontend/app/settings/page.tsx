"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import Shell from "@/components/Shell";
import { api } from "@/lib/api";
import { errMsg, short } from "@/lib/format";
import { useSession } from "@/lib/hooks";
import { clearSession, saveSession } from "@/lib/session";
import { isLocalDemoEnabled } from "@/lib/demo";
import { assertRegistryDeployed, connect, ensureDemoRequesterRegistered } from "@/lib/wallet";

export default function SettingsPage() {
  const router = useRouter();
  const { session, error: walletError } = useSession(["patient", "clinician", "facility"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function connectWallet() {
    if (!session) return;
    const role = session.role;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const wallet = await connect();
      const address = await wallet.getAddress();
      if (role === "clinician") await ensureDemoRequesterRegistered(wallet);
      else await assertRegistryDeployed(wallet);
      const { message } = await api.walletLinkNonce(address);
      const signature = await wallet.signMessage(message);
      const { token } = await api.linkWallet(address, signature);
      const updated = saveSession(token);
      if (!updated.address || updated.address.toLowerCase() !== address.toLowerCase()) {
        clearSession();
        throw new Error("The server did not confirm the linked wallet.");
      }
      setSuccess(`Connected ${short(address)}. Opening your dashboard…`);
      router.push(updated.role === "patient" ? "/patient" : "/clinician");
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  if (!session) return null;
  return (
    <Shell session={session} title="Account settings">
      {error && <div className="notice error" role="alert">{error}</div>}
      {walletError && <div className="notice error" role="alert">{walletError}</div>}
      {success && <div className="notice success" role="status">{success}</div>}

      <section className="panel settings-card">
        <span className="chip">{session.role === "patient" ? "Data owner" : "Data requester"}</span>
        <h2>Wallet</h2>
        {session.email && <p><strong>Email:</strong> {session.email}</p>}
        {session.address ? (
          <p>Linked wallet: <code>{session.address}</code></p>
        ) : (
          <p className="muted">
            {session.role === "clinician" && isLocalDemoEnabled()
              ? "Connect any Anvil wallet. If it is unregistered, confirm the transaction to register it as a requester."
              : "Connect the wallet registered for this account to use consent, records, and audit features."}
          </p>
        )}
        {session.email ? (
          <button onClick={connectWallet} disabled={busy}>
            {busy ? "Check your wallet…" : session.address ? "Verify wallet" : "Connect wallet"}
          </button>
        ) : (
          <p className="muted">This account is already authenticated with its connected wallet.</p>
        )}
      </section>

      {session.address && (
        <p className="muted settings-back"><Link href={session.role === "patient" ? "/patient" : "/clinician"}>Back to dashboard</Link></p>
      )}
    </Shell>
  );
}
