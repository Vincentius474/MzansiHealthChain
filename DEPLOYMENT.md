# MzansiHealthChain Deployment Guide

## Deployment architecture

- GitHub: source control and deployment trigger.
- Vercel: Next.js frontend.
- Render: FastAPI backend.
- Render Persistent Disk: encrypted record files and SQLite workflow database.
- Avalanche Fuji: smart contracts and blockchain interactions.

The current deployment targets Fuji testnet (Chain ID 43113), not Avalanche Mainnet.

## 1. Avalanche Fuji contracts

Network configuration:

- Network: Avalanche Fuji C-Chain
- Chain ID: 43113
- Currency: AVAX
- RPC: https://api.avax-test.network/ext/bc/C/rpc

Deployed contracts:

| Contract | Address |
|---|---|
| PatientRegistry | `0x132F4C91dDE9b5aff8499950bFc0D44DAF333Ed7` |
| ConsentManagement | `0x975bf7eC0EDf7FFd91248C75dA7700F8C236a0f2` |
| AccessControl | `0x22d84f4F8fbAe2d6782EE0cc27cD1Cc02ceE271` |
| AuditLog | `0x4f5Dd3c21E4f602b7f7c33d06928E8A7bE876E88` |

The contracts have been deployed and verified on Fuji. Run `forge test` from the `contracts/` directory before making contract changes.

Do not use these addresses as Mainnet deployments.

## 2. Deploy the backend to Render

Create a new Web Service in Render and connect the GitHub repository.

Configure:

- Runtime: Docker
- Root Directory: `backend`
- Dockerfile Path: `Dockerfile`
- Branch: `main`
- Health Check Path: `/health`

The Dockerfile uses Render's assigned `PORT` environment variable.

### Persistent disk

Attach a persistent disk to the backend service:

- Mount Path: `/var/data`
- Set the environment variable `DATA_DIR=/var/data`

The directory stores:
- Encrypted health-record blobs.
- `workflow.sqlite3`.

Do not use an ephemeral filesystem for these records. Start with one backend instance because SQLite and login nonces are currently process-local.

### Backend environment variables

Configure these in Render's Environment settings. Never commit production secrets.

| Variable | Value |
|---|---|
| `RPC_URL` | `https://api.avax-test.network/ext/bc/C/rpc` |
| `REGISTRY_ADDR` | Fuji PatientRegistry address above |
| `CONSENT_ADDR` | Fuji ConsentManagement address above |
| `ACCESS_ADDR` | Fuji AccessControl address above |
| `AUDIT_ADDR` | Fuji AuditLog address above |
| `DATA_DIR` | `/var/data` |
| `CORS_ORIGINS` | Your exact Vercel frontend URL |
| `AUDIT_FROM_BLOCK` | `0` initially; adjust if required by RPC limits |
| `DEMO_AUTH_ENABLED` | `false` |
| `JWT_SECRET` | Independently generated random secret |
| `MASTER_KEY_HEX` | Independently generated 32-byte key encoded as 64 hexadecimal characters |
| `RELAYER_PRIVATE_KEY` | Dedicated Fuji relayer private key |

AI configuration:

- `OLLAMA_URL`: URL reachable from the Render service if using a separately hosted Ollama instance.
- `OLLAMA_MODEL`: model available at that Ollama endpoint.
- `GROQ_API_KEY`, `GEMINI_API_KEY`, `TAVILY_API_KEY`: configure only if those integrations are intended to be enabled.

Ollama running on your personal computer at `localhost` is not reachable from Render. Do not assume the local Ollama instance will work after deployment. Sensitive patient information must not be sent to external AI providers.

Do not set `PORT` manually; Render supplies it.

## 3. Deploy the frontend to Vercel

Import the GitHub repository into Vercel.

Configure:

- Framework Preset: Next.js
- Root Directory: `frontend`
- Build Command: `npm run build`
- Install Command: `npm ci`
- Production Branch: `main`

Set these environment variables in Vercel:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | Your Render backend URL |
| `NEXT_PUBLIC_REGISTRY_ADDR` | `0x132F4C91dDE9b5aff8499950bFc0D44DAF333Ed7` |
| `NEXT_PUBLIC_CONSENT_ADDR` | `0x975bf7eC0EDf7FFd91248C75dA7700F8C236a0f2` |
| `NEXT_PUBLIC_ACCESS_ADDR` | `0x22d84f4F8fbAe2d6782EE0cc27cD1Cc02ceE271` |
| `NEXT_PUBLIC_AUDIT_ADDR` | `0x4f5Dd3c21E4f602b7f7c33d06928E8A7bE876E88` |
| `NEXT_PUBLIC_CHAIN_ID` | `43113` |
| `NEXT_PUBLIC_RPC_URL` | `https://api.avax-test.network/ext/bc/C/rpc` |
| `NEXT_PUBLIC_DEMO_AUTH_ENABLED` | `false` |
| `NEXT_PUBLIC_START_BLOCK` | `0` initially; replace with deployment block if appropriate |

These `NEXT_PUBLIC_` variables are exposed in browser code. Never put private keys, API secrets, JWT secrets, or encryption keys in them.

After setting the Render URL, ensure the backend's `CORS_ORIGINS` contains the exact Vercel production origin. Redeploy the backend after changing environment variables.

Vercel embeds public environment variables during the build, so redeploy the frontend after changing them.

## 4. Verify the deployment

1. Open the Render service health endpoint: `/health`.
2. Confirm the backend can connect to Avalanche Fuji.
3. Open the Vercel frontend.
4. Connect Core Wallet and select Avalanche Fuji.
5. Confirm the frontend can read the deployed contracts.
6. Test authentication and permitted record workflows using fictional data.
7. Confirm encrypted files and the SQLite database persist across backend restarts.

## 5. Security and production limitations

This deployment is for testnet demonstration and testing, not production health-record processing.

Before using real patient data, complete security, privacy, and regulatory reviews. In particular:

- Use a secure key-management strategy such as KMS/HSM for encryption keys.
- Protect the relayer private key and limit its permissions and funds.
- Add shared nonce storage before running multiple backend instances.
- Establish backups and recovery procedures for the persistent disk and SQLite database.
- Review authentication, authorization, rate limiting, logging, and data-retention controls.
- Do not send identifiable patient information to external AI services.

Public blockchain transactions, wallet addresses, consent events, record hashes, and audit events are visible on-chain and cannot be removed.
