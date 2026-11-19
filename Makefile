# MzansiHealthChainlocal development. Uses anvil's PUBLIC dev keys: never use them on a real network.
ANVIL_RPC        = http://127.0.0.1:8545
DEPLOYER_KEY     = 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
PATIENT_KEY      = 0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d
RELAYER_ADDR     = 0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC
CLINICIAN_ADDR   = 0x90F79bf6EB2c4f870365E785982E1f101E93b906

.PHONY: test-all frontend-check clean help install test test-v gas coverage fmt anvil deploy-local seed-local backend backend-test frontend e2e

help:
	@grep -E '^[a-z-]+:' Makefile | cut -d: -f1 | tr '\n' ' '; echo

install:
	cd contracts && forge install foundry-rs/forge-std --no-git
	cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
	cd frontend && npm install

# ---- contracts
test:
	cd contracts && forge test
test-v:
	cd contracts && forge test -vvv
gas:
	cd contracts && forge test --gas-report
coverage:
	cd contracts && forge coverage
fmt:
	cd contracts && forge fmt

# ---- local chain (run `make anvil` in its own terminal)
anvil:
	anvil
deploy-local:
	cd contracts && DEPLOYER_PRIVATE_KEY=$(DEPLOYER_KEY) RELAYER_ADDRESS=$(RELAYER_ADDR) \
		forge script script/Deploy.s.sol --rpc-url $(ANVIL_RPC) --broadcast
	python3 scripts/sync_env.py 31337
seed-local:
	cd contracts && DEPLOYER_PRIVATE_KEY=$(DEPLOYER_KEY) PATIENT_PRIVATE_KEY=$(PATIENT_KEY) CLINICIAN_ADDRESS=$(CLINICIAN_ADDR) \
		forge script script/Seed.s.sol --rpc-url $(ANVIL_RPC) --broadcast

# ---- backend / frontend
backend:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000
backend-test:
	cd backend && . .venv/bin/activate && pytest -q
frontend:
	cd frontend && npm run dev

# ---- checks
test-all: test backend-test frontend-check
frontend-check:
	cd frontend && npm run typecheck
clean:
	rm -rf contracts/out contracts/cache backend/data frontend/.next

# ---- whole-system check (needs anvil + deploy + seed + backend running)
e2e:
	cd backend && . .venv/bin/activate && python ../scripts/e2e_local.py
