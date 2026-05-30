# build.ps1 — local build orchestrator for Buddy Desktop Pet
#
#   1. Activates the virtual env  (creates one if missing)
#   2. Installs PyInstaller
#   3. Runs PyInstaller using build/Buddy.spec  →  dist/Buddy/
#   4. (Optional) Runs Inno Setup Compiler      →  build/Output/BuddySetup-<ver>.exe
#
# Usage:
#   .\build\build.ps1                         # build .exe only
#   .\build\build.ps1 -Installer              # also build BuddySetup.exe
#   .\build\build.ps1 -Installer -Version 0.2.0
#
# Requires:
#   - Python 3.11+  on PATH
#   - For -Installer:  Inno Setup 6  (https://jrsoftware.org/isdl.php)

[CmdletBinding()]
param(
    [switch] $Installer,
    [string] $Version = "0.1.0",
    [switch] $Clean
)

$ErrorActionPreference = "Stop"
$ROOT = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $ROOT

Write-Host "==> Build root: $ROOT" -ForegroundColor Cyan

# ── Clean previous artefacts ────────────────────────────────────────────────
if ($Clean) {
    Write-Host "==> Cleaning previous build output" -ForegroundColor Cyan
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue dist, build\Output, build\__pycache__
}

# ── Virtual env ─────────────────────────────────────────────────────────────
if (-not (Test-Path ".venv")) {
    Write-Host "==> Creating virtual env" -ForegroundColor Cyan
    python -m venv .venv
}
& ".\.venv\Scripts\Activate.ps1"

# ── Dependencies ────────────────────────────────────────────────────────────
Write-Host "==> Installing dependencies" -ForegroundColor Cyan
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
python -m pip install pyinstaller --quiet

# ── Regenerate sprites (cheap; ensures dist is fresh) ───────────────────────
Write-Host "==> Regenerating sprites" -ForegroundColor Cyan
python sprite_gen.py

# ── PyInstaller ─────────────────────────────────────────────────────────────
Write-Host "==> Running PyInstaller" -ForegroundColor Cyan
pyinstaller build\Buddy.spec --noconfirm --clean

if (-not (Test-Path "dist\Buddy\Buddy.exe")) {
    throw "PyInstaller did not produce dist\Buddy\Buddy.exe"
}
Write-Host "==> Built dist\Buddy\Buddy.exe" -ForegroundColor Green

# ── Inno Setup (optional) ───────────────────────────────────────────────────
if ($Installer) {
    Write-Host "==> Building installer (version $Version)" -ForegroundColor Cyan

    # Locate ISCC.exe
    $iscc = $null
    foreach ($p in @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )) {
        if (Test-Path $p) { $iscc = $p; break }
    }
    if (-not $iscc) {
        throw "Inno Setup 6 not found. Install from https://jrsoftware.org/isdl.php"
    }

    $env:BUDDY_VERSION = $Version
    & $iscc build\installer.iss

    $output = Get-ChildItem build\Output\BuddySetup-*.exe -ErrorAction SilentlyContinue |
              Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($output) {
        Write-Host "==> Installer ready: $($output.FullName)" -ForegroundColor Green
        Write-Host "    Size: $([math]::Round($output.Length / 1MB, 1)) MB" -ForegroundColor Green
    } else {
        throw "Inno Setup did not produce an installer."
    }
}

Write-Host "==> Build complete." -ForegroundColor Green
