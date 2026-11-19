"use client";

import { Contract, isAddress, JsonRpcSigner } from "ethers";
import Link from "next/link";
import { FormEvent, useState } from "react";
import { ADDR, REGISTRY_ABI, ROLE } from "@/lib/contracts";
import { errMsg, short } from "@/lib/format";
import { connect } from "@/lib/wallet";

export default function AdminPage() {
  const [signer, setSigner] = useState<JsonRpcSigner | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [address, setAddress] = useState("");
  const [newAdminAddress, setNewAdminAddress] = useState("");
  const [role, setRole] = useState<number>(ROLE.Clinician);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  async function connectWallet() {
    setError(null);
    try {
      const s = await connect();
      const registry = new Contract(ADDR.registry, REGISTRY_ABI, s);
      setIsAdmin(
        (await registry.admin()).toLowerCase() === s.address.toLowerCase()
      );
      setSigner(s);
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function register(e: FormEvent) {
    e.preventDefault();
    if (!signer) return;
    if (!isAddress(address)) {
      return setError("Enter the full wallet address.");
    }

    setBusy(true);
    setError(null);
    setOk(null);

    try {
      const registry = new Contract(ADDR.registry, REGISTRY_ABI, signer);
      await (await registry.registerProvider(address, role)).wait();

      setOk(
        `${short(address)} is now a registered ${
          role === ROLE.Clinician ? "clinician" : "facility"
        }.`
      );
      setAddress("");
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  }

  async function transferAdmin(e: FormEvent) {
    e.preventDefault();
    if (!signer || !isAdmin) return;

    if (!isAddress(newAdminAddress)) {
      return setError("Enter a valid administrator wallet address.");
    }

    if (newAdminAddress.toLowerCase() === signer.address.toLowerCase()) {
      return setError("The new administrator must be a different wallet.");
    }

    if (
      !window.confirm(
        `Transfer Registry administration to ${newAdminAddress}? This action requires an on-chain transaction.`
      )
    ) {
      return;
    }

    setBusy(true);
    setError(null);
    setOk(null);

    try {
      const registry = new Contract(ADDR.registry, REGISTRY_ABI, signer);
      await (await registry.transferAdmin(newAdminAddress)).wait();

      setOk(
        `Registry administration successfully transferred to ${short(
          newAdminAddress
        )}. Reconnect using the new administrator wallet.`
      );
      setNewAdminAddress("");
      setIsAdmin(false);
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page">
      <h1>Registry administration</h1>
      <p className="muted">
        Manage registered healthcare providers and transfer Registry
        administration.
      </p>

      {error && <div className="notice error" role="alert">{error}</div>}
      {ok && <div className="notice success" role="status">{ok}</div>}

      {!signer ? (
        <button onClick={connectWallet}>
          Connect administrator wallet
        </button>
      ) : isAdmin ? (
        <>
          <section className="panel">
            <h2>Register a clinician or facility</h2>
            <p className="muted">
              Check provider credentials before registration.
            </p>

            <form onSubmit={register}>
              <label>
                Wallet address
                <input
                  value={address}
                  onChange={(e) => setAddress(e.target.value.trim())}
                  placeholder="0x..."
                  autoComplete="off"
                />
              </label>

              <label>
                Type
                <select
                  value={role}
                  onChange={(e) => setRole(Number(e.target.value))}
                >
                  <option value={ROLE.Clinician}>Clinician</option>
                  <option value={ROLE.Facility}>
                    Facility (hospital, lab, pharmacy)
                  </option>
                </select>
              </label>

              <div>
                <button disabled={busy}>
                  {busy ? "Confirm in your wallet..." : "Register provider"}
                </button>
              </div>
            </form>
          </section>

          <section className="panel" style={{ marginTop: "1.5rem" }}>
            <h2>Transfer Registry administrator</h2>
            <p className="muted">
              Transfer administrative authority to another wallet. The new
              administrator will be able to manage provider registrations.
            </p>

            <form onSubmit={transferAdmin}>
              <label>
                New administrator wallet address
                <input
                  value={newAdminAddress}
                  onChange={(e) =>
                    setNewAdminAddress(e.target.value.trim())
                  }
                  placeholder="0x..."
                  autoComplete="off"
                />
              </label>

              <div>
                <button disabled={busy}>
                  {busy
                    ? "Confirm in your wallet..."
                    : "Transfer administration"}
                </button>
              </div>
            </form>
          </section>
        </>
      ) : (
        <div className="notice error" role="alert">
          This wallet is not the registry administrator.
        </div>
      )}

      <p style={{ marginTop: "2rem" }}>
        <Link href="/">Back to sign in</Link>
      </p>
    </main>
  );
}
