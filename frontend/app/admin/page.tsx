"use client";
import { Contract, isAddress, JsonRpcSigner } from "ethers";
import Link from "next/link";
import { FormEvent, useState } from "react";
import { ADDR, REGISTRY_ABI, ROLE } from "@/lib/contracts";
import { errMsg, short } from "@/lib/format";
import { connect } from "@/lib/wallet";

/** Registry admin tools. Uses the wallet directly; no app session is needed. */
export default function AdminPage() {
  const [signer, setSigner] = useState<JsonRpcSigner | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [address, setAddress] = useState("");
  const [role, setRole] = useState<number>(ROLE.Clinician);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  async function connectWallet() {
    setError(null);
    try {
      const s = await connect();
      const registry = new Contract(ADDR.registry, REGISTRY_ABI, s);
      setIsAdmin((await registry.admin()).toLowerCase() === s.address.toLowerCase());
      setSigner(s);
    } catch (e) { setError(errMsg(e)); }
  }

  async function register(e: FormEvent) {
    e.preventDefault();
    if (!signer) return;
    if (!isAddress(address)) return setError("Enter the full wallet address.");
    setBusy(true); setError(null); setOk(null);
    try {
      const registry = new Contract(ADDR.registry, REGISTRY_ABI, signer);
      await (await registry.registerProvider(address, role)).wait();
      setOk(`${short(address)} is now a registered ${role === ROLE.Clinician ? "clinician" : "facility"}.`);
      setAddress("");
    } catch (err) { setError(errMsg(err)); }
    finally { setBusy(false); }
  }

  return (
    <main className="page">
      <h1>Register a clinician</h1>
      <p className="muted">Only the registry administrator wallet can do this. Check credentials before registering.</p>
      {error && <div className="notice error" role="alert">{error}</div>}
      {ok && <div className="notice success" role="status">{ok}</div>}

      {!signer ? (
        <button onClick={connectWallet}>Connect administrator wallet</button>
      ) : isAdmin ? (
        <form className="panel" onSubmit={register}>
          <label>Wallet address
            <input value={address} onChange={(e) => setAddress(e.target.value.trim())} placeholder="0x…" autoComplete="off" />
          </label>
          <label>Type
            <select value={role} onChange={(e) => setRole(Number(e.target.value))}>
              <option value={ROLE.Clinician}>Clinician</option>
              <option value={ROLE.Facility}>Facility (hospital, lab, pharmacy)</option>
            </select>
          </label>
          <div><button disabled={busy}>{busy ? "Confirm in your wallet…" : "Register"}</button></div>
        </form>
      ) : (
        <div className="notice error" role="alert">This wallet is not the registry administrator.</div>
      )}
      <p style={{ marginTop: "2rem" }}><Link href="/">Back to sign in</Link></p>
    </main>
  );
}
