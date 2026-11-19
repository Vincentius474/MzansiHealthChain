# MzansiHealthChain: local setup and verification

> **Windows?** There is no `make`. Use `run <task>` instead and follow [SETUP-WINDOWS.md](SETUP-WINDOWS.md).

Goal: get contracts, backend and the AI pipeline working **locally** before touching any cloud
deployment. Everything below runs on your machine with a local chain (anvil).

## 1. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Foundry (forge, anvil) | recent | `forge --version` |
| Python | 3.11+ (built with 3.12) | `python3 --version` |
| Node.js | 20+ | `node --version` |
| Ollama | recent | `ollama --version` |
| Core Wallet | browser extension | needed only for the UI, not for the e2e script |

Install Foundry: `curl -L https://foundry.paradigm.xyz | bash` then `foundryup`.

## 2. Install dependencies

    make install

This installs forge-std, creates `backend/.venv` with the backend and test dependencies, and runs
`npm install` in `frontend/`. Then pull a local model once:

    ollama pull llama3.1:8b

## 3. Verify the contracts (no chain needed)

    make test          # all tests
    make test-v        # with traces, use when something fails
    make gas           # gas report
    make coverage      # line/branch coverage

What the suite covers (`contracts/test/`):

| File | Covers |
|---|---|
| PatientRegistry.t.sol | patient/provider registration, duplicate IDs, role overwrite protection, provider removal, admin transfer, fuzz |
| ConsentManagement.t.sol | grant/revoke rules, expiry boundary, 365-day cap, per-patient and per-provider isolation, fuzz on the consent window |
| AccessControl.t.sol | consent-gated writes and reads, input validation, revoked/expired/removed providers, patient self-view, fuzz on callers |
| AuditLog.t.sol | logger-only writes, denied-attempt logging, counters, owner controls |
| Integration.t.sol | the full lifecycle from the sequence diagram, plus a check that the backend relayer cannot touch consent or records |

## 4. Verify the backend logic (no chain, no Ollama needed)

    make backend-test

Covers AES-256-GCM (round trip, tamper detection, patient binding), wallet-signature login (replay,
wrong signer, expiry, unregistered wallet), de-identification, model routing (decrypted data only
reaches Ollama) and the agent pipeline with chain/storage/LLM mocked.

## 5. Run the whole system locally

Use four terminals, from the repo root.

**Terminal 1: local chain**

    make anvil

**Terminal 2: deploy, seed, start the backend**

    make deploy-local     # deploys 4 contracts, writes contracts/deployments/31337.json,
                          # creates backend/.env and frontend/.env.local (secrets generated)
    make seed-local       # registers a demo clinician and patient; no access is granted yet
    make backend          # http://127.0.0.1:8000  (docs at /docs)

**Terminal 3: Ollama** (if it is not already running as a service)

    ollama serve

**Terminal 4: end-to-end check**

    make e2e

Expected flow: unregistered wallet gets 403, clinician logs in, a record is encrypted and anchored
on-chain, the AI summary is produced and audited, the patient revokes consent, the next request is a
403 and that denied attempt is audited, consent is restored. The summary step is skipped with a
message if Ollama is not reachable; use `python scripts/e2e_local.py --require-ai` to make that a
failure.

## 6. Demo accounts (local anvil only)

These are anvil's public dev keys. They are worthless on any real network.

| Role | Anvil account | Address |
|---|---|---|
| Deployer / registry admin | #0 | 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 |
| Demo patient | #1 | 0x70997970C51812dc3A010C7d01b50e0d17dc79C8 |
| Backend relayer (audit logger) | #2 | 0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC |
| Demo clinician | #3 | 0x90F79bf6EB2c4f870365E785982E1f101E93b906 |

To use the UI against anvil, add a custom network in Core (RPC `http://127.0.0.1:8545`, chain ID
`31337`) and import the patient/clinician private keys printed by `anvil`. If your Core version does
not offer private-key import, rely on the e2e script, which signs with the same keys without a browser.

## 6b. Try the UI (optional, needs Core Wallet or MetaMask)

    make frontend        # http://localhost:3000

`make deploy-local` already wrote `frontend/.env.local`. Then, with the wallet on the local network:

1. **Choose a role** (`/`), then sign in on `/login/data-owner` or `/login/data-requester` with the matching
   local demo credentials below. If a browser wallet is installed, the app detects it and asks to connect
   and sign a wallet-link message. If there is no extension or you decline, go to **Settings** after sign-in.
   Wallet linking accepts any address registered on local Anvil for the matching role: Patient for the
   data owner, Clinician for the data requester. For the default demo, use the seeded patient (#1) and
   clinician (#3) accounts listed above; connecting a wallet alone does not register it on-chain.
   On chain ID `31337`, a new requester wallet can register itself as a Clinician after you confirm the
   transaction in your wallet. This is a local-demo-only contract feature; redeploy the updated contracts
   and run `make seed-local` before using it.
2. **Admin** (`/admin`): connect the deployer wallet (anvil #0) and register your clinician wallet.
   `make seed-local` already did this for the demo clinician.
3. **Data requester** (`/clinician`): use the patient-provided wallet address to request selected record
   categories, explain the care purpose, choose a duration, and optionally mark the request urgent.
   Urgent requests still require the owner's approval.
4. **Data owner** (`/patient`): review the purpose and requested scope, select the categories to share,
   approve a duration in Core Wallet, or deny the request. The owner can also add encrypted records,
   filter records by category/provider/date, flag an entry, and export their records.
5. **Data requester** (`/clinician`): load only approved categories, view records, add append-only
   clinical notes, generate summaries, and review audited activity and notifications.
6. **Data owner** again: review access history and notifications, and withdraw active consent at any time.

Local demo credentials (public, only for local Anvil):

| Role | Email | Password |
|---|---|---|
| Data owner / patient | `owner@demo.mzansihealthchain.local` | `OwnerDemo2026!` |
| Data requester / clinician | `requester@demo.mzansihealthchain.local` | `RequesterDemo2026!` |

These demo passwords are not suitable for deployment. Email/password sign-in is enabled only for local Anvil.

Backend endpoints behind this (all JSON, interactive docs at `http://127.0.0.1:8000/docs`):

| Endpoint | Who | Purpose |
|---|---|---|
| POST /auth/email-login | local demo users | email/password sign-in, returns unlinked JWT |
| POST /auth/wallet/nonce, /auth/wallet/link | signed-in demo user | prove wallet ownership and link it to the account |
| POST /auth/nonce, /auth/login | wallet-based API clients | wallet-signature login, returns linked JWT |
| GET /auth/me | signed in | role, email, and linked address |
| POST /access-requests | provider | request specific categories and a time limit; no records returned |
| GET /access-requests/inbox, /mine | owner / provider | view incoming and submitted requests |
| POST /access-requests/{id}/approve or /deny | patient owner | save owner decision; approval requires matching on-chain consent |
| POST /records/encrypt | owner or provider with scoped approval | encrypt + store a text record and its metadata |
| GET /owner/records, /owner/export | that patient only | decrypt own records or download JSON export |
| GET /records/{patient} | provider with scoped approval | approved record metadata only; storage refs hidden |
| GET /records/{patient}/{id} | provider with scoped approval | decrypt an approved record and audit the read |
| POST /agent/summary | provider with scoped approval | summarize only approved categories; audit |
| GET /audit/{patient} | that patient only | who accessed, including denied attempts |
| GET /requester/audit | signed-in provider | the provider's own audited activity |
| GET /notifications | signed in | request, decision, record-access, and flag notifications |

## 7. Running on Avalanche Fuji instead of anvil

1. Create three wallets: deployer (admin), relayer, and your own patient/clinician wallets.
2. Fund deployer and relayer with Fuji test AVAX from the Avalanche testnet faucet.
3. Deploy:

       cd contracts
       export DEPLOYER_PRIVATE_KEY=0x... RELAYER_ADDRESS=0x...
       forge script script/Deploy.s.sol --rpc-url fuji --broadcast
       cd .. && python3 scripts/sync_env.py 43113

4. Open `backend/.env` and set `RELAYER_PRIVATE_KEY` to the relayer wallet key (sync does not set it
   for Fuji). Keep these keys out of git; `.gitignore` already excludes `.env` files.
5. Register your clinician wallet as a provider from the deployer wallet and the patient wallet with
   `registerPatient`. The provider requests access in the app; the patient approves it from their dashboard.
   Deploy the updated contracts before using patient self-upload.

## 8. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `forge test` cannot find `forge-std` | run `make install`. If `--no-git` is rejected by your Foundry version, run `git init` in the repo root and use plain `forge install foundry-rs/forge-std` |
| `make deploy-local` fails to connect | anvil is not running in another terminal |
| Backend crashes at start with a validation error | `backend/.env` missing values; run `make deploy-local` or `python3 scripts/sync_env.py 31337` |
| Login returns 403 "wallet not registered on-chain" | wallet has no role; run `make seed-local` or register it |
| `/agent/summary` returns 403 | patient has no active consent for that clinician (expected after revoke or expiry) |
| `/agent/summary` returns 500 | Ollama not running or model not pulled; check `OLLAMA_URL` and `OLLAMA_MODEL` |
| Relayer audit transaction fails on Fuji | relayer wallet has no test AVAX, or is not set as logger in AuditLog |
| `forge script` cannot write `deployments/` | `fs_permissions` is set in `foundry.toml`; run the script from `contracts/` |

## 9. Design notes and known limits

- Everything on-chain is public. Hashes, storage references and audit events reveal that a record or
  access exists, never its content.
- `getRecords(provider, patient)` takes the provider as a parameter so the backend can check on a
  clinician's behalf. It is a policy gate, not secrecy.
- The backend relayer can only write audit entries. Consent changes need the patient's own wallet;
  provider registration needs the admin wallet.
- An approval is scoped to selected categories in the backend workflow database. The current Solidity
  consent contract grants access per patient/provider pair, so the backend filters before decrypting;
  it does not make the on-chain consent itself category-specific. Keep storage private and do not treat
  public chain references as a confidentiality boundary.
- Request metadata, free-text titles, purposes, and flag reasons are stored in the local
  `backend/data/workflow.sqlite3` database; free-text fields are encrypted with the configured master
  key. Preserve that database and the master key together if keeping a local demo.
- Emergency requests are marked urgent but never bypass owner approval.
- The master encryption key comes from an env variable. A KMS-held key is the production upgrade.
- De-identification is regex-based (IDs, emails, phones, wallets). Names and addresses need an NER step
  before any real data goes to a cloud model.
- The UI reads consent and audit history straight from chain events. On public RPCs that cap
  `eth_getLogs` ranges, set `NEXT_PUBLIC_START_BLOCK` (frontend) and `AUDIT_FROM_BLOCK` (backend) to the
  block where you deployed.
- Records are plain text notes in this version. File upload (PDF, images, FHIR bundles) is the natural next step.
- Nonces for wallet login live in backend memory, so restarting the backend invalidates in-flight logins.
  Multiple backend instances would need a shared store.
