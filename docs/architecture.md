# MzansiHealthChain: Architecture and Workflows

This document describes the implemented application: role-based dashboards, consent and record workflows, the backend, smart contracts, off-chain storage, and AI integrations.

## System architecture

```mermaid
flowchart LR
  subgraph Client["Browser application"]
    Owner["Data Owner"]
    Requester["Data Requester"]
    Admin["Registry admin"]
    UI["Next.js app<br/>login, dashboards, settings"]
    Wallet["Core Wallet / MetaMask<br/>EIP-1193 signer"]
    Owner --> UI
    Requester --> UI
    Admin --> UI
    UI -->|connect and sign prompts| Wallet
    Wallet -->|signature results| UI
  end

  subgraph Backend["FastAPI backend"]
    API["HTTP API"]
    Auth["Authentication<br/>wallet signatures and JWT"]
    Workflow["Workflow service"]
    ChainClient["chain.py<br/>Web3 reads and relayed audit writes"]
    Crypto["crypto.py<br/>AES-256-GCM and SHA-256"]
    Agents["agents.py<br/>consent, retrieval, analysis, audit"]
    LLM["llm.py<br/>model routing and search"]
    API --> Auth
    API --> Workflow
    API --> ChainClient
    API --> Crypto
    API --> Agents
    Agents --> ChainClient
    Agents --> Crypto
    Agents --> LLM
  end

  subgraph Offchain["Off-chain data"]
    DB[("SQLite<br/>requests, scopes, metadata,<br/>notifications and flags")]
    Blobs[("Encrypted record blobs<br/>local storage or Spaces")]
    Workflow --> DB
    Crypto -->|encrypt and decrypt| Blobs
    Agents -->|retrieve ciphertext| Blobs
  end

  subgraph EVM["Avalanche C-Chain or local Anvil"]
    Registry["PatientRegistry<br/>roles"]
    Consent["ConsentManagement<br/>patient-provider expiry"]
    Access["AccessControl<br/>record hashes and references"]
    Audit["AuditLog<br/>access events"]
    Consent --> Registry
    Access --> Registry
    Access --> Consent
  end

  subgraph AI["AI and external services"]
    Ollama["Ollama<br/>local model for sensitive summaries"]
    Cloud["Groq / Gemini<br/>optional non-sensitive prompts"]
    Tavily["Tavily<br/>optional general-topic search"]
    LLM -->|sensitive prompt| Ollama
    LLM -.->|non-sensitive prompt only| Cloud
    LLM -.->|topic query only| Tavily
  end

  UI -->|JSON API plus JWT| API
  Wallet -->|signed consent and record transactions| EVM
  ChainClient -->|JSON-RPC reads| EVM
  ChainClient -.->|audit writes via relayer| Audit
```

## Access request and summary workflow

```mermaid
sequenceDiagram
  actor Requester
  actor Owner as Data Owner
  participant UI as Next.js
  participant API as FastAPI
  participant DB as Workflow SQLite
  participant Wallet as Browser wallet
  participant Chain as Smart contracts
  participant Store as Encrypted storage
  participant Ollama as Local Ollama
  participant Tavily as Tavily

  Requester->>UI: Sign in with requester account
  UI->>API: POST /auth/email-login
  API-->>UI: Unlinked JWT
  opt New requester wallet on local Anvil
    UI->>Wallet: Request Clinician registration
    Wallet->>Chain: registerLocalDemoClinician()
    Chain-->>Wallet: Registration confirmed
  end
  UI->>API: Request wallet-link nonce
  API-->>UI: Nonce message
  UI->>Wallet: Sign nonce
  Wallet-->>UI: Signature
  UI->>API: Verify signature and wallet role
  API-->>UI: Linked JWT

  Requester->>UI: Patient, purpose, categories, duration
  UI->>API: POST /access-requests
  API->>Chain: Verify patient registration
  API->>DB: Store pending request and owner notification
  Owner->>UI: Review request and requested scope
  alt Owner denies
    Owner->>API: POST /access-requests/{id}/deny
    API->>DB: Mark denied and notify requester
  else Owner approves
    Owner->>Wallet: Confirm consent transaction
    Wallet->>Chain: ConsentManagement.grant(provider, expiry)
    Owner->>API: POST /access-requests/{id}/approve
    API->>Chain: Verify on-chain consent expiry
    API->>DB: Store approved categories and expiry
    API->>DB: Notify requester
  end

  Requester->>UI: Read records or request summary
  UI->>API: Request with linked JWT
  API->>Chain: Check active consent and read record references
  API->>DB: Resolve approved category scope
  API->>API: Filter records before decryption
  API->>Store: Fetch encrypted blobs
  API->>API: Verify SHA-256, then decrypt in memory
  API->>Ollama: Approved records and clinical question
  Ollama-->>API: Summary with record citations
  opt Requester entered a general topic
    API->>Tavily: Search topic only
    Tavily-->>API: General references
  end
  API->>Chain: Write access audit event via relayer
  API-->>Requester: Summary, references, and trace
```

## Record creation and storage

```mermaid
sequenceDiagram
  actor User as Owner or authorized requester
  participant UI as Next.js
  participant API as FastAPI
  participant Crypto as AES-GCM service
  participant Store as Off-chain storage
  participant Wallet as Browser wallet
  participant Chain as AccessControl
  participant DB as Workflow SQLite

  User->>UI: Enter record text and metadata
  UI->>API: POST /records/encrypt
  API->>API: Check role, consent, and category scope
  API->>Crypto: Encrypt content bound to patient wallet
  Crypto->>Store: Save encrypted blob
  API->>DB: Save record metadata
  API-->>UI: Return ciphertext hash and opaque storage reference
  UI->>Wallet: Request addRecord transaction
  Wallet->>Chain: Anchor hash and storage reference
  Chain-->>UI: RecordAdded event
```

## Authorization and data boundaries

- The owner signs consent grants and revocations. The backend and AI agents cannot change consent.
- `AccessControl` stores hashes and opaque references, not record contents. Record blobs are encrypted off-chain.
- The contract consent is patient-provider wide. Category-level scope and expiry are additionally enforced by the backend workflow store before records are decrypted.
- Sensitive summary prompts use local Ollama. Groq and Gemini are available only for non-sensitive prompts; the current patient-record summary path does not send records to them.
- Tavily receives the optional topic query, not retrieved record content. Keep that topic generic and do not enter patient identifiers.
- AI output is assistive and must be checked against source records. Agents cannot approve requests, grant access, or write records.
- `registerLocalDemoClinician()` is restricted to chain ID `31337`; public-chain provider registration remains an administrator operation.

## Role capabilities

| Capability | Data Owner / Patient | Data Requester / Clinician | Registry admin | Backend relayer |
|---|---|---|---|---|
| Upload records | Own records | With active consent and approved category | | |
| Request access | | Yes, with purpose, categories, and duration | | |
| Approve, deny, or revoke access | Own records only | | | |
| View records and request summaries | Own records | Approved scope only | | |
| Flag records, export, view audit | Own records | Own audited activity | | |
| Register patient wallet | Self-register on-chain | | | |
| Register providers | | Local Anvil self-registration only for demo | Register/remove providers | |
| Write audit events | | | | Yes |

## Code map

| Concern | Where |
|---|---|
| Identity and on-chain roles | `contracts/src/PatientRegistry.sol` |
| Consent grant, revoke, and expiry | `contracts/src/ConsentManagement.sol` |
| Record references and contract access checks | `contracts/src/AccessControl.sol` |
| Append-only access trail | `contracts/src/AuditLog.sol` |
| Wallet linking and JWTs | `backend/app/auth.py` |
| Chain reads and audit writes | `backend/app/chain.py` |
| AES-256-GCM and SHA-256 | `backend/app/crypto.py` |
| Requests, scopes, metadata, notifications, and flags | `backend/app/workflow.py` |
| Storage backends | `backend/app/storage.py` |
| Model routing and Tavily | `backend/app/llm.py` |
| Summary orchestration and agents | `backend/app/agents.py` |
| HTTP API and authorization gates | `backend/app/main.py` |
| Role dashboards and wallet helpers | `frontend/app/`, `frontend/lib/` |
