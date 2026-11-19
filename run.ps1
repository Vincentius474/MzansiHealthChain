<#
.SYNOPSIS
  Windows replacement for `make`. Same task names as the Makefile.
.EXAMPLE
  .\run.ps1 install
  .\run.ps1 test
  .\run.ps1 e2e -RequireAi
  (or use run.cmd:  run test)
#>
param(
    [Parameter(Position = 0)][string]$Task = "help",
    [switch]$RequireAi
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

# Anvil's PUBLIC dev keys. Local testing only; never use them on a real network.
$AnvilRpc      = "http://127.0.0.1:8545"
$DeployerKey   = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
$PatientKey    = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
$RelayerAddr   = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"
$ClinicianAddr = "0x90F79bf6EB2c4f870365E785982E1f101E93b906"

$VenvPy = Join-Path $Root "backend\.venv\Scripts\python.exe"

# Foundry's default install folder (used by `install-foundry` and foundryup)
$FoundryBin = Join-Path $env:USERPROFILE ".foundry\bin"
if ((Test-Path $FoundryBin) -and (($env:Path -split ";") -notcontains $FoundryBin)) { $env:Path = "$FoundryBin;$env:Path" }

function Get-SystemPython {
    # Returns @{ Exe = ...; Args = ... }. "python" can be the Microsoft Store stub, so check it really runs.
    try {
        if (Get-Command python -ErrorAction SilentlyContinue) {
            & python --version *> $null
            if ($LASTEXITCODE -eq 0) { return [pscustomobject]@{ Exe = "python"; Args = @() } }
        }
    } catch { }
    if (Get-Command py -ErrorAction SilentlyContinue) { return [pscustomobject]@{ Exe = "py"; Args = @("-3") } }
    throw "Python 3.11+ not found. Install it from python.org and tick 'Add python.exe to PATH'."
}

function Require-Tool([string]$name, [string]$hint) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        throw "'$name' was not found on PATH. $hint"
    }
}

function Require-Venv {
    if (-not (Test-Path $VenvPy)) { throw "Backend environment missing. Run: .\run.ps1 install" }
}

# Run a native command in a sub-folder and stop if it fails.
function Exec([string]$Dir, [scriptblock]$Cmd) {
    Push-Location (Join-Path $Root $Dir)
    try {
        $global:LASTEXITCODE = 0
        & $Cmd
        if ($LASTEXITCODE -ne 0) { throw "Command failed (exit code $LASTEXITCODE)" }
    } finally { Pop-Location }
}

switch ($Task) {

    "help" {
        Write-Host "Tasks:"
        Write-Host "  install-foundry  download Foundry (forge, anvil) for Windows"
        Write-Host "  install        forge-std, backend venv + packages, frontend packages"
        Write-Host "  test           contract tests            (test-v: verbose, gas, coverage)"
        Write-Host "  backend-test   backend tests"
        Write-Host "  frontend-check TypeScript check"
        Write-Host "  test-all       all three of the above"
        Write-Host "  anvil          local chain (leave running in its own window)"
        Write-Host "  deploy-local   deploy contracts to anvil, write .env files"
        Write-Host "  seed-local     demo clinician, patient and consent"
        Write-Host "  backend        API on http://127.0.0.1:8000"
        Write-Host "  frontend       UI on http://localhost:3000"
        Write-Host "  e2e            full-flow check (add -RequireAi to fail if Ollama is down)"
        Write-Host "  clean          remove build output"
    }

    "install-foundry" {
        # Foundry's own installer (foundryup) does not run in PowerShell, so fetch the official Windows build.
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        New-Item -ItemType Directory -Force $FoundryBin | Out-Null
        Write-Host "Looking up the latest Foundry release..."
        $rel = Invoke-RestMethod "https://api.github.com/repos/foundry-rs/foundry/releases/latest" -Headers @{ "User-Agent" = "MzansiHealthChain-setup" }
        $asset = $rel.assets | Where-Object { $_.name -like "*win32_amd64.zip" } | Select-Object -First 1
        if (-not $asset) { throw "No Windows download found in release $($rel.tag_name). Download it manually from https://github.com/foundry-rs/foundry/releases/latest" }
        $zip = Join-Path $env:TEMP $asset.name
        Write-Host "Downloading $($asset.name) ($($rel.tag_name))..."
        Invoke-WebRequest $asset.browser_download_url -OutFile $zip
        Expand-Archive $zip -DestinationPath $FoundryBin -Force
        Remove-Item $zip -ErrorAction SilentlyContinue
        $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
        if (-not $userPath) { $userPath = "" }
        if (($userPath -split ";") -notcontains $FoundryBin) {
            [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(";") + ";" + $FoundryBin), "User")
        }
        $env:Path = "$FoundryBin;$env:Path"
        & (Join-Path $FoundryBin "forge.exe") --version
        & (Join-Path $FoundryBin "anvil.exe") --version
        Write-Host "`
Foundry installed to $FoundryBin. Now run: .\run install"
    }

    "install" {
        Require-Tool forge "Run: .\run install-foundry"
        Require-Tool git   "forge-std is downloaded with git. Install Git for Windows."
        Require-Tool npm   "Install Node.js 20+ from nodejs.org."
        if (-not (Test-Path (Join-Path $Root "contracts\lib\forge-std"))) {
            Exec "contracts" { forge install foundry-rs/forge-std --no-git }
        } else { Write-Host "forge-std already installed" }
        if (-not (Test-Path $VenvPy)) {
            $py = Get-SystemPython
            $exe = $py.Exe
            $pyArgs = $py.Args
            Exec "backend" { & $exe @pyArgs -m venv .venv }
        }
        Exec "backend" { & $VenvPy -m pip install --upgrade pip }
        Exec "backend" { & $VenvPy -m pip install -r requirements-dev.txt }
        Exec "frontend" { npm install }
        Write-Host "`nInstall complete. Next: .\run.ps1 test"
    }

    "test"    { Exec "contracts" { forge test } }
    "test-v"  { Exec "contracts" { forge test -vvv } }
    "gas"     { Exec "contracts" { forge test --gas-report } }
    "coverage" { Exec "contracts" { forge coverage } }

    "backend-test" {
        Require-Venv
        Exec "backend" { & $VenvPy -m pytest -q }
    }

    "frontend-check" { Exec "frontend" { npm run typecheck } }

    "test-all" {
        & $PSCommandPath test
        & $PSCommandPath backend-test
        & $PSCommandPath frontend-check
    }

    "anvil" {
        Require-Tool anvil "Run: .\run install-foundry"
        anvil
    }

    "deploy-local" {
        Require-Venv
        $env:DEPLOYER_PRIVATE_KEY = $DeployerKey
        $env:RELAYER_ADDRESS = $RelayerAddr
        try {
            Exec "contracts" { forge script script/Deploy.s.sol --rpc-url $AnvilRpc --broadcast }
        } finally {
            Remove-Item Env:DEPLOYER_PRIVATE_KEY, Env:RELAYER_ADDRESS -ErrorAction SilentlyContinue
        }
        Exec "." { & $VenvPy scripts\sync_env.py 31337 }
    }

    "seed-local" {
        $env:DEPLOYER_PRIVATE_KEY = $DeployerKey
        $env:PATIENT_PRIVATE_KEY = $PatientKey
        $env:CLINICIAN_ADDRESS = $ClinicianAddr
        try {
            Exec "contracts" { forge script script/Seed.s.sol --rpc-url $AnvilRpc --broadcast }
        } finally {
            Remove-Item Env:DEPLOYER_PRIVATE_KEY, Env:PATIENT_PRIVATE_KEY, Env:CLINICIAN_ADDRESS -ErrorAction SilentlyContinue
        }
    }

    "backend" {
        Require-Venv
        Exec "backend" { & $VenvPy -m uvicorn app.main:app --reload --port 8000 }
    }

    "frontend" { Exec "frontend" { npm run dev } }

    "e2e" {
        Require-Venv
        if ($RequireAi) { Exec "backend" { & $VenvPy ..\scripts\e2e_local.py --require-ai } }
        else            { Exec "backend" { & $VenvPy ..\scripts\e2e_local.py } }
    }

    "clean" {
        foreach ($p in "contracts\out", "contracts\cache", "backend\data", "frontend\.next") {
            Remove-Item (Join-Path $Root $p) -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Host "cleaned"
    }

    default { Write-Host "Unknown task '$Task'. Try: .\run.ps1 help"; exit 1 }
}
