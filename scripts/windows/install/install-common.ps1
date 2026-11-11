# Shared helpers for PTP component installers.
# Compatible with Windows PowerShell 5.1.

$script:PtpRoot = Split-Path -Parent $PSScriptRoot
$script:ComponentsPath = Join-Path $script:PtpRoot "components.json"

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:HF_HOME = Join-Path $script:PtpRoot "data\hf-cache"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Fail {
    param([string]$Message)
    Write-Error $Message
    exit 1
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Force -Path $Path | Out-Null
    }
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Read-Components {
    if (-not (Test-Path -LiteralPath $script:ComponentsPath)) {
        Fail "components.json not found: $script:ComponentsPath"
    }
    return Get-Content -LiteralPath $script:ComponentsPath -Raw | ConvertFrom-Json
}

function Write-ComponentMarker {
    param(
        [string]$Path,
        [hashtable]$Data
    )
    Ensure-Directory (Split-Path -Parent $Path)
    $payload = [ordered]@{
        installed_at = (Get-Date).ToString("o")
        component = $Data
    }
    $payload | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Confirm-License {
    param(
        [string]$Name,
        [string]$LicensePath,
        [string]$Url,
        [switch]$AcceptLicense
    )
    Write-Host ""
    Write-Host "$Name license: $Url" -ForegroundColor Yellow
    if ($LicensePath -and (Test-Path -LiteralPath $LicensePath)) {
        Write-Host "Local license: $LicensePath"
    }
    if ($AcceptLicense) {
        return
    }
    if (-not [Environment]::UserInteractive) {
        Fail "License acceptance required. Re-run with -AcceptLicense."
    }
    $answer = Read-Host "Type Y to accept the $Name license"
    if ($answer -notin @("Y", "y", "yes", "YES")) {
        Fail "License not accepted."
    }
}
