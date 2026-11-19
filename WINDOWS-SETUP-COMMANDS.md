# Native Windows Setup Commands

Run these commands from the `MzansiHealthChain` project folder.

## Check prerequisites

```powershell
git --version
python --version
node --version
npm --version
ollama --version
```

## Install Foundry

```powershell
.\run.cmd install-foundry
```

Open a new terminal if `forge` or `anvil` is not found.

## Install project dependencies

```powershell
.\run.cmd install
```

## Download the AI model

```powershell
ollama pull llama3.1:8b
```

## Run tests

```powershell
.\run.cmd test-all
```

Or run the suites separately:

```powershell
.\run.cmd test
.\run.cmd backend-test
.\run.cmd frontend-check
```

## Start the local application

Run each command in a separate PowerShell or Command Prompt window.

### Terminal 1: local blockchain

```powershell
.\run.cmd anvil
```

### Terminal 2: deploy and seed

```powershell
.\run.cmd deploy-local
.\run.cmd seed-local
.\run.cmd backend
```

### Terminal 3: AI service

```powershell
ollama serve
```

### Terminal 4: end-to-end check

```powershell
.\run.cmd e2e
```

To require Ollama to succeed:

```powershell
.\run.cmd e2e -RequireAi
```

## Optional frontend

Run in a separate terminal:

```powershell
.\run.cmd frontend
```

The frontend will be available at `http://localhost:3000`.

Choose the data-owner or data-requester sign-in page and use its prefilled email/password. If Core Wallet
or MetaMask is installed, the app asks to connect it after sign-in; otherwise connect it in **Settings**.
The public local-demo credentials are in `SETUP.md`; never use them outside Anvil.
