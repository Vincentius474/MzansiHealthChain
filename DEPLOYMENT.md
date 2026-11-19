# Avalanche C-Chain and Vercel deployment

This project deploys its Solidity contracts to Avalanche C-Chain. Vercel hosts the Next.js frontend;
the FastAPI backend and its persistent data must be hosted separately.

## Avalanche Mainnet contracts

Avalanche C-Chain Mainnet uses chain ID `43114`, AVAX, and the RPC
`https://api.avax.network/ext/bc/C/rpc`. Fuji testnet uses chain ID `43113`; test there before
deploying to Mainnet. The Foundry and wallet configurations in this project include both networks.

1. Run the contract suite from `contracts/` with `forge test`.
2. Create a dedicated deployer wallet, fund it with AVAX, and create a separate relayer wallet.
   The deployer is initially the PatientRegistry administrator and AuditLog owner. The relayer
   receives permission to write audit events. Do not reuse local Anvil keys or commit private keys.
3. Configure `DEPLOYER_PRIVATE_KEY` and `RELAYER_ADDRESS` in the deployment shell's environment,
   then deploy from the `contracts/` directory:

   ```powershell
   $env:DEPLOYER_PRIVATE_KEY = "<securely supplied deployer private key>"
   $env:RELAYER_ADDRESS = "<relayer public address>"
   forge script script/Deploy.s.sol --rpc-url mainnet --broadcast
   ```

   The script writes the deployed contract addresses to
   `contracts/deployments/43114.json`. Treat the deployer key as a temporary privileged key; transfer
   admin/ownership to an appropriately secured multisig after deployment.
4. From the project root, sync the deployment addresses into local environment files:

   ```powershell
   python scripts/sync_env.py 43114
   ```

   This updates `backend/.env` and `frontend/.env.local`; do not commit either file. Use separately
   generated production secrets in your hosting providers, rather than copying local development
   secrets. Do not run `Seed.s.sol` with demo accounts on Mainnet.

Use the official [Avalanche network reference](https://build.avax.network/docs/primary-network) for
network details. Public contract state, wallet addresses, consent events, record hashes/references,
and audit events are visible on-chain and cannot be removed.

## Deploy the frontend to Vercel

1. Import the repository in Vercel and select the Next.js project root. If the repository root is
   this project directory, set **Root Directory** to `frontend`; if the repository contains this
   project in a subdirectory, use `MzansiHealthChain/frontend`.
2. Keep Vercel's detected Next.js framework, build command, and output settings.
3. Add the values from `frontend/.env.vercel.example` to the Vercel project's **Production**
   environment. Replace the backend URL and all four contract addresses with the deployed values.
   Set `NEXT_PUBLIC_START_BLOCK` to the deployment block if the selected RPC provider limits event
   query ranges. These `NEXT_PUBLIC_` values are included in browser code; never put secrets in them.
4. Deploy and verify the site connects to chain ID `43114`, switches the wallet to Avalanche C-Chain,
   and can read the deployed PatientRegistry.

Vercel reads `NEXT_PUBLIC_` values during the build, so redeploy after changing them. Configure
Preview and Development environments separately; do not point previews at production data unless
that is intentional.

## Host the backend separately

The existing [backend/Dockerfile](backend/Dockerfile) can be used to deploy FastAPI to a container
host. Vercel deployment of the Next.js frontend does not deploy this API. Configure these backend
environment variables in the backend host's secret manager:

- `RPC_URL=https://api.avax.network/ext/bc/C/rpc`
- `REGISTRY_ADDR`, `CONSENT_ADDR`, `ACCESS_ADDR`, and `AUDIT_ADDR` from the Mainnet deployment
- `RELAYER_PRIVATE_KEY` for the dedicated relayer; keep it secret and funded for audit transactions
- Independently generated `JWT_SECRET` and `MASTER_KEY_HEX`; use a KMS/HSM-backed key strategy before
  handling real health data
- `CORS_ORIGINS` set to the exact Vercel production origin, for example
  `https://your-project.vercel.app` (comma-separated only when multiple trusted origins are needed)
- `AUDIT_FROM_BLOCK` set to the deployment block when the RPC provider requires bounded log queries
- `SPACES_ENDPOINT`, `SPACES_BUCKET`, `SPACES_KEY`, and `SPACES_SECRET` for durable encrypted blob
  storage; do not rely on container-local files for persistent records

The current workflow database is SQLite at `backend/data/workflow.sqlite3`. Run the backend only on
infrastructure with persistent storage until the application is migrated to a production database;
ephemeral/serverless filesystems can lose workflow data. The backend also keeps login nonces in
process memory, so multiple instances need shared nonce storage before horizontal scaling.

Before using real patient data, complete security, privacy, and regulatory reviews. The project's
[threat model](docs/threat-model.md) lists known gaps, including key management, rate limiting, and
in-memory nonces. Deployment configuration alone does not make the application production-ready for
regulated health data.
