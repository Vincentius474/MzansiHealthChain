
"use client";

import { Contract, isAddress, JsonRpcSigner } from "ethers";
import Link from "next/link";
import { FormEvent, useState } from "react";
import {
  ADDR,
  AUDIT_ABI,
  REGISTRY_ABI,
  ROLE,
} from "@/lib/contracts";
import { errMsg, short } from "@/lib/format";
import { connect } from "@/lib/wallet";

const ADMIN = "0x33A435Ac7a03630dEB2c8F69FDedFc58B9212351";
const CLINICIAN = "0xA54e001cFC6C37Bf7482EE0cc27cD1Cc02ceE271";
const RELAYER = "0x688f0C459f69dFB358f9998a70904d50CEbea5F2";
const PATIENT = "0x8f10a57fe090f3D417BB65764AB0a267c4aFe6b0";

const ACCOUNTS = [
  { name: "Administrator", address: ADMIN },
  { name: "Clinician", address: CLINICIAN },
  { name: "Relayer", address: RELAYER },
  { name: "Patient", address: PATIENT },
];

export default function AdminPage() {
  const [signer, setSigner] = useState<JsonRpcSigner | null>(null);
  const [connectedAddress, setConnectedAddress] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);

  const [auditOwner, setAuditOwner] = useState("");
  const [isAuditOwner, setIsAuditOwner] = useState(false);
  const [loggerStatus, setLoggerStatus] = useState<Record<string, boolean>>({});

  const [address, setAddress] = useState("");
  const [newAdminAddress, setNewAdminAddress] = useState("");
  const [role, setRole] = useState<number>(ROLE.Clinician);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  async function refreshStatus(s: JsonRpcSigner) {
    const account = await s.getAddress();

    const registry = new Contract(ADDR.registry, REGISTRY_ABI, s);
    const audit = new Contract(ADDR.audit, AUDIT_ABI, s);

    const [registryAdmin, owner] = await Promise.all([
      registry.admin(),
      audit.owner(),
    ]);

    const statuses: Record<string, boolean> = {};

    for (const item of ACCOUNTS) {
      statuses[item.address.toLowerCase()] = await audit.isLogger(
        item.address
      );
    }

    setConnectedAddress(account);
    setIsAdmin(registryAdmin.toLowerCase() === account.toLowerCase());
    setAuditOwner(owner);
    setIsAuditOwner(owner.toLowerCase() === account.toLowerCase());
    setLoggerStatus(statuses);
  }

  async function connectWallet() {
    setError(null);
    setOk(null);

    try {
      const s = await connect();
      await refreshStatus(s);
      setSigner(s);
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function register(e: FormEvent) {
    e.preventDefault();
    if (!signer || !isAdmin) return;

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

    if (newAdminAddress.toLowerCase() === connectedAddress.toLowerCase()) {
      return setError("The new administrator must be a different wallet.");
    }

    if (
      !window.confirm(
        `Transfer Registry administration to ${newAdminAddress}?`
      )
    ) return;

    setBusy(true);
    setError(null);
    setOk(null);

    try {
      const registry = new Contract(ADDR.registry, REGISTRY_ABI, signer);
      await (await registry.transferAdmin(newAdminAddress)).wait();

      setOk(
        `Registry administration transferred to ${short(newAdminAddress)}.`
      );
      setNewAdminAddress("");
      await refreshStatus(signer);
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  }

  async function transferAuditOwnership() {
    if (!signer || !isAuditOwner) return;

    if (
      !window.confirm(
        `Transfer AuditLog ownership to the Administrator ${ADMIN}? The current owner will lose permission to manage logger accounts.`
      )
    ) return;

    setBusy(true);
    setError(null);
    setOk(null);

    try {
      const audit = new Contract(ADDR.audit, AUDIT_ABI, signer);
      await (await audit.transferOwnership(ADMIN)).wait();

      setOk(
        "AuditLog ownership transferred to the Administrator. Reconnect using the Administrator wallet to manage logger permissions."
      );

      await refreshStatus(signer);
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  }

  async function changeLogger(account: string, allowed: boolean) {
    if (!signer || !isAuditOwner) return;

    const accountName =
      ACCOUNTS.find(
        (item) => item.address.toLowerCase() === account.toLowerCase()
      )?.name ?? short(account);

    const action = allowed ? "authorise" : "revoke";

    if (
      !window.confirm(
        `Are you sure you want to ${action} ${accountName} as an AuditLog logger?`
      )
    ) return;

    setBusy(true);
    setError(null);
    setOk(null);

    try {
      const audit = new Contract(ADDR.audit, AUDIT_ABI, signer);
      await (await audit.setLogger(account, allowed)).wait();

      await refreshStatus(signer);

      setOk(
        `${accountName} logger permission successfully ${
          allowed ? "enabled" : "revoked"
        }.`
      );
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page admin-page">
      <h1>MzansiHealthChain Administration</h1>

      <p className="muted">
        Manage healthcare providers, Registry administration and blockchain
        audit permissions.
      </p>

      {error && <div className="notice error" role="alert">{error}</div>}
      {ok && <div className="notice success" role="status">{ok}</div>}

      {!signer ? (
        <button onClick={connectWallet}>
          Connect administrator or contract owner wallet
        </button>
      ) : (
        <>
          <section className="panel">
            <h2>Connected wallet</h2>
            <p>{connectedAddress}</p>
            <p className="muted">
              Registry administrator: {isAdmin ? "Yes" : "No"}
            </p>
            <p className="muted">
              AuditLog owner: {isAuditOwner ? "Yes" : "No"}
            </p>
            <button
              type="button"
              className="secondary"
              onClick={connectWallet}
              disabled={busy}
            >
              Refresh / reconnect wallet
            </button>
          </section>

          {isAdmin && (
            <>
              <section className="panel" style={{ marginTop: "1.5rem" }}>
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

                  <button disabled={busy}>
                    {busy ? "Confirm in your wallet..." : "Register provider"}
                  </button>
                </form>
              </section>

              <section className="panel" style={{ marginTop: "1.5rem" }}>
                <h2>Transfer Registry administrator</h2>
                <p className="muted">
                  This changes Registry administration only. It does not
                  change AuditLog ownership.
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

                  <button disabled={busy}>
                    {busy
                      ? "Confirm in your wallet..."
                      : "Transfer Registry administration"}
                  </button>
                </form>
              </section>
            </>
          )}

          <section className="panel" style={{ marginTop: "1.5rem" }}>
            <h2>AuditLog management</h2>

            <p className="muted">
              Contract: {ADDR.audit}
            </p>

            <p>
              <strong>Current AuditLog owner:</strong>
              <br />
              {auditOwner || "Loading..."}
            </p>

            {isAuditOwner ? (
              <>
                {auditOwner.toLowerCase() !== ADMIN.toLowerCase() && (
                  <div style={{ marginTop: "1rem" }}>
                    <h3>Transfer AuditLog ownership</h3>
                    <p className="muted">
                      Transfer ownership to the designated Administrator.
                      The Administrator can then manage logger permissions.
                    </p>

                    <button
                      type="button"
                      disabled={busy}
                      onClick={transferAuditOwnership}
                    >
                      {busy
                        ? "Confirm in your wallet..."
                        : "Transfer AuditLog ownership to Administrator"}
                    </button>
                  </div>
                )}

                {auditOwner.toLowerCase() === ADMIN.toLowerCase() && (
                  <>
                    <h3>Logger permissions</h3>
                    <p className="muted">
                      Only the authorised Relayer should write audit events.
                    </p>

                    {ACCOUNTS.map((item) => {
                      const enabled =
                        loggerStatus[item.address.toLowerCase()] ?? false;

                      return (
                        <div
                          key={item.address}
                          style={{
                            borderTop: "1px solid var(--border, #ddd)",
                            padding: "1rem 0",
                          }}
                        >
                          <strong>{item.name}</strong>
                          <p className="muted">{item.address}</p>
                          <p>
                            Logger status:{" "}
                            <strong>{enabled ? "Enabled" : "Disabled"}</strong>
                          </p>

                          <button
                            type="button"
                            disabled={busy || enabled}
                            onClick={() => changeLogger(item.address, true)}
                          >
                            Authorise logger
                          </button>{" "}

                          <button
                            type="button"
                            className="secondary"
                            disabled={busy || !enabled}
                            onClick={() => changeLogger(item.address, false)}
                          >
                            Revoke logger
                          </button>
                        </div>
                      );
                    })}
                  </>
                )}
              </>
            ) : (
              <p className="muted">
                Connect the current AuditLog owner wallet to manage these
                settings. Only the on-chain owner can change logger permissions.
              </p>
            )}
          </section>
        </>
      )}

      <p style={{ marginTop: "2rem" }}>
        <Link href="/">Back to sign in</Link>
      </p>
    </main>
  );
}
