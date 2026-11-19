"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ReactNode } from "react";
import { short } from "@/lib/format";
import { clearSession, Session } from "@/lib/session";

const ROLE_LABEL = { patient: "Patient", clinician: "Clinician", facility: "Facility" };

export default function Shell({ session, title, children }: { session: Session; title: string; children: ReactNode }) {
  const router = useRouter();
  return (
    <>
      <header className="bar">
        <span className="brand">
          <img className="platform-logo header-logo" src="/logo.png" alt="" />
          <span>MzansiHealthChain</span>
        </span>
        <span className="who">
          {ROLE_LABEL[session.role]} · {session.email ?? (session.address ? short(session.address) : "Wallet not linked")}
        </span>
        <Link href="/settings">Settings</Link>
        <button className="link" onClick={() => { clearSession(); router.push("/"); }}>Sign out</button>
      </header>
      <main className="page">
        <h1>{title}</h1>
        {children}
      </main>
    </>
  );
}
