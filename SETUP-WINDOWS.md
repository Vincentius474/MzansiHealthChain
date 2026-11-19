# MzansiHealthChainon Windows

`make` doesn't exist on Windows, so this project ships `run.ps1` (and a `run.cmd` wrapper) with the
same task names. Everywhere `SETUP.md` says `make <task>`, type `run <task>` instead.

| SETUP.md | Windows |
|---|---|
| `make install` | `run install` |
| (no make equivalent) | `run install-foundry` |
| `make test` | `run test` |
| `make backend-test` | `run backend-test` |
| `make frontend-check` | `run frontend-check` |
| `make anvil` | `run anvil` |
| `make deploy-local` | `run deploy-local` |
| `make seed-local` | `run seed-local` |
| `make backend` | `run backend` |
| `make frontend` | `run frontend` |
| `make e2e` | `run e2e` (add `-RequireAi` to fail when Ollama is down) |

Run `run help` for the full list. Use `run` in Command Prompt, or `.\run` in PowerShell.

## Two ways to set up

### Option B: native Windows with `run.ps1`

**Install once**

| Tool | Notes |
|---|---|
| Git for Windows | needed by `forge install` |
| Python 3.11+ | from python.org; tick "Add python.exe to PATH". Skip the Microsoft Store version |
| Node.js 20+ | from nodejs.org |
| Foundry | run `.\run install-foundry` (downloads the official Windows build into `%USERPROFILE%\.foundry\bin` and adds it to PATH). **Do not paste the `curl` command from Foundry's website into PowerShell.** That installer only works in Git Bash or WSL |
| Ollama | Windows installer from ollama.com, then `ollama pull llama3.1:8b` |

Open a **new** terminal after installing so PATH updates apply, then check:

    git --version
    python --version
    node --version
    forge --version
    anvil --version

**Run it** (from the project folder, use separate windows where noted). In PowerShell write `.\run`, in Command Prompt `run`.

    run install-foundry   <- once, if `forge --version` fails
    run install
    run test
    run backend-test
    run frontend-check

    run anvil            <- window 1, leave running
    run deploy-local     <- window 2
    run seed-local
    run backend          <- leave running
    run e2e              <- window 3 (Ollama running)
    run frontend         <- optional UI at http://localhost:3000

The backend runs from its own virtual environment, so you never need to activate it.
On local Anvil, choose the data-owner or data-requester sign-in page and use its email/password form.
If Core Wallet or MetaMask is installed, the app detects it after sign-in and asks to connect the matching
wallet. The connected address must already be registered on Anvil as a patient (owner) or clinician
(requester); use the seeded patient and clinician accounts listed in `SETUP.md` for the default demo.
On chain ID `31337`, an unregistered requester wallet can self-register as a clinician after you confirm
the transaction in your wallet. This local-demo-only feature requires redeploying the updated contracts
with `run deploy-local`, then running `run seed-local`.
If no extension is available or the connection is declined, use **Settings** to connect later.
Run `run seed-local` first. Seeding registers the demo roles but does not grant consent: a requester
must ask for selected categories and the owner must approve them in their dashboard. Urgent requests
still require owner approval. Demo credentials and addresses are listed in `SETUP.md`; they are only
for local Anvil and must not be used in a real deployment.

## Windows troubleshooting

| Symptom | Fix |
|---|---|
| `'run' is not recognized` | in PowerShell type `.\run` (with the dot and backslash). Also make sure you are in the folder that contains `run.cmd` |
| "running scripts is disabled" when using `.\run.ps1` | use `run <task>` (the wrapper bypasses the policy), or run `Unblock-File .\run.ps1` |
| `'forge' was not found` | open a new terminal; check `%USERPROFILE%\.foundry\bin` is on PATH; or switch to Option A |
| `curl: A parameter cannot be found that matches parameter name 'L'` | you pasted the Foundry installer into PowerShell. Use `.\run install-foundry` instead |
| `install-foundry` cannot reach GitHub | check internet/proxy, or download `win32_amd64.zip` from github.com/foundry-rs/foundry/releases/latest and unzip it into `%USERPROFILE%\.foundry\bin` |
| Python not found, or the Microsoft Store opens | install Python from python.org with PATH ticked; or disable the "python.exe" App execution aliases in Windows settings |
| `pip install` fails building a package | use Python 3.12 (not a very new pre-release) and rerun `run install` |
| `forge install` fails | Git for Windows missing or no internet; if `--no-git` is rejected by your version, run `git init` in the project root and `forge install foundry-rs/forge-std` inside `contracts` |
| Port 8545, 8000 or 3000 already in use | close the old window, or run `netstat -ano` and look for the port number |
| Windows Firewall prompt for anvil/node/python | allow on private networks; everything runs on localhost |
| Frontend build cannot fetch the font | it downloads Atkinson Hyperlegible from Google Fonts on first run; check your internet connection |
| Antivirus quarantines `forge.exe` or `anvil.exe` | add an exception for `%USERPROFILE%\.foundry` |

Everything else (accounts, UI walkthrough, endpoints, design notes) is in `SETUP.md`.
