import Link from "next/link";

export default function Home() {
  return (
    <main className="page signin-page">
      <div className="signin-brand">
        <img className="platform-logo signin-logo" src="/logo.png" alt="" />
        <span><strong>MzansiHealthChain</strong><small>Patient-controlled health records</small></span>
      </div>
      <div className="hero">
        <h1>Your health records. Your say on who sees them.</h1>
        <p>
          Sign in to manage your health information or request access as a clinician.
          Wallet approval is handled securely after sign-in.
        </p>
      </div>
      <section className="login-grid" aria-label="Choose your account type">
        <article className="panel login-card">
          <span className="chip">Data owner</span>
          <h2>Participant</h2>
          <p className="muted">Manage consent and see who has accessed your records.</p>
          <Link className="button-link" href="/login/data-owner">Continue as data owner</Link>
        </article>
        <article className="panel login-card">
          <span className="chip">Data requester</span>
          <h2>Clinician</h2>
          <p className="muted">Check consent, add clinical records, and request summaries.</p>
          <Link className="button-link" href="/login/data-requester">Continue as data requester</Link>
        </article>
      </section>
      <p className="muted demo-hint">You can connect a Core Wallet or MetaMask after signing in.</p>
    </main>
  );
}
