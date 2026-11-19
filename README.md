# MzansiHealthChain: Agentic Healthcare Platform

Blockchain-based patient consent, encrypted off-chain records and consent-gated AI summaries.

On Windows (no `make`), read **[SETUP-WINDOWS.md](SETUP-WINDOWS.md)** and use `run <task>`.

Start with **[SETUP.md](SETUP.md)**: install, run the contract and backend tests, then run the whole
system locally and verify it with `make e2e`.

    make install && make test && make backend-test

For Avalanche C-Chain Mainnet and Vercel deployment, see **[DEPLOYMENT.md](DEPLOYMENT.md)**.

Layout: `contracts/` (Solidity + Foundry tests), `backend/` (FastAPI, agents, crypto, tests),
`frontend/` (Next.js + Core Wallet: sign-in, patient dashboard, clinician view, admin), `scripts/` (env sync, secrets, e2e check).

See **[Architecture and workflow diagrams](docs/architecture.md)** for the system design, access lifecycle, and record/AI data flows.
