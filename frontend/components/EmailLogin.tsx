"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { isLocalDemoEnabled } from "@/lib/demo";
import { errMsg } from "@/lib/format";
import { assertRegistryDeployed, ensureDemoRequesterRegistered, hasWalletExtension, connect } from "@/lib/wallet";
import { clearSession, saveSession } from "@/lib/session";

type LoginRole = "patient" | "clinician";
type Props = { role: LoginRole };

const DEMO_ACCOUNTS: Record<LoginRole, { email: string; password: string }> = {
  patient: {
    email: "owner@demo.mzansihealthchain.local",
    password: "OwnerDemo2026!",
  },
  clinician: {
    email: "requester@demo.mzansihealthchain.local",
    password: "RequesterDemo2026!",
  },
};

const ROLE_COPY: Record<LoginRole, { title: string; label: string; description: string; button: string }> = {
  patient: {
    title: "Data owner sign in",
    label: "Participant",
    description: "Manage consent and review access to your records.",
    button: "Sign in as data owner",
  },
  clinician: {
    title: "Data requester sign in",
    label: "Clinician",
    description: "Request access to patient records and manage clinical notes.",
    button: "Sign in as data requester",
  },
};

async function linkDetectedWallet(role: LoginRole) {
  const wallet = await connect();
  const address = await wallet.getAddress();
  if (role === "clinician") await ensureDemoRequesterRegistered(wallet);
  else await assertRegistryDeployed(wallet);
  const { message } = await api.walletLinkNonce(address);
  const signature = await wallet.signMessage(message);
  const { token } = await api.linkWallet(address, signature);
  const session = saveSession(token);
  if (session.role !== role || !session.address || session.address.toLowerCase() !== address.toLowerCase()) {
    clearSession();
    throw new Error("The connected wallet does not match this account. Check the wallet and try again.");
  }
}

export default function EmailLogin({ role }: Props) {
  const router = useRouter();
  const [credentials, setCredentials] = useState(DEMO_ACCOUNTS[role]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [continueToSettings, setContinueToSettings] = useState(false);
  const localLoginEnabled = isLocalDemoEnabled();
  const copy = ROLE_COPY[role];

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setContinueToSettings(false);
    try {
      const { token } = await api.emailLogin(credentials.email, credentials.password, role);
      const session = saveSession(token);
      if (session.role !== role || !session.email || session.address) {
        clearSession();
        throw new Error("The server returned an invalid sign-in session.");
      }

      if (hasWalletExtension()) {
        try {
          await linkDetectedWallet(role);
          router.push(role === "patient" ? "/patient" : "/clinician");
          return;
        } catch (walletError) {
          setError(`You are signed in, but wallet connection was not completed. Connect it in Settings. ${errMsg(walletError)}`);
          setContinueToSettings(true);
          return;
        }
      }

      router.push("/settings");
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page signin-page">
      <div className="signin-brand">
        <img className="platform-logo signin-logo" src="/logo.png" alt="" />
        <span><strong>MzansiHealthChain</strong><small>Patient-controlled health records</small></span>
      </div>
      <div className="hero">
        <p className="eyebrow">{copy.label}</p>
        <h1>{copy.title}</h1>
        <p>{copy.description}</p>
      </div>

      {error && <div className="notice error" role="alert">{error}</div>}
      {!localLoginEnabled && (
        <div className="notice" role="status">
          Email/password demo accounts are enabled only on local Anvil. Configure the local development environment to sign in.
        </div>
      )}

      <form className="panel sign-in-form" onSubmit={submit}>
        <label>Email
          <input
            type="email"
            autoComplete="username"
            required
            value={credentials.email}
            onChange={(event) => setCredentials({ ...credentials, email: event.target.value })}
          />
        </label>
        <label>Password
          <input
            type="password"
            autoComplete="current-password"
            required
            value={credentials.password}
            onChange={(event) => setCredentials({ ...credentials, password: event.target.value })}
          />
        </label>
        <button disabled={busy || !localLoginEnabled}>
          {busy ? "Signing in…" : copy.button}
        </button>
      </form>

      {continueToSettings && <button className="secondary settings-continue" onClick={() => router.push("/settings")}>Continue to Settings</button>}
      <p className="muted wallet-note">
        If Core Wallet or MetaMask is installed, the app will ask to connect it after sign-in. A new requester wallet can register as a clinician on local Anvil after you confirm a transaction. You can also connect later in Settings.
      </p>
      <p className="signin-links">
        <Link href="/">Choose another account type</Link>
      </p>
    </main>
  );
}
