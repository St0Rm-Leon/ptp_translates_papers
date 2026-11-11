[CmdletBinding()]
param(
    [string]$ModelDir = "",
    [string]$Revision = "",
    [switch]$Force,
    [switch]$DryRun
)

. (Join-Path $PSScriptRoot "install-common.ps1")

$components = Read-Components
$hy = $components.hy_model
$modelsDir = Join-Path $PtpRoot "models"
$target = Join-Path $modelsDir $hy.filename
$licensePath = Join-Path $PtpRoot "LICENSES\Apache-2.0.txt"

Write-Host ""
Write-Host "Hy-MT2 model: $($hy.repo)" -ForegroundColor Yellow
Write-Host "License: Apache-2.0 (see $licensePath)"
Write-Host "Source: https://huggingface.co/$($hy.repo)"

if ((Test-Path -LiteralPath $target) -and -not $Force) {
    Write-Step "Checking existing Hy-MT2 model"
    $actual = Get-Sha256 $target
    if ($actual -eq $hy.sha256) {
        Write-Host "Hy-MT2 already installed: $target" -ForegroundColor Green
        Write-ComponentMarker (Join-Path $modelsDir ".ptp-component.json") @{
            name = "hy-model"
            repo = $hy.repo
            revision = $hy.revision
            sha256 = $actual
            path = $target
        }
        return
    }
    Write-Host "Existing model hash differs; replacing it." -ForegroundColor Yellow
}

if ($DryRun) {
    Write-Step "Dry run: Hy-MT2 install plan"
    if ($ModelDir) {
        Write-Host "Would copy from: $ModelDir"
    } else {
        Write-Host "Would download $($hy.repo)@$($hy.revision) to $modelsDir"
    }
    Write-Host "Target: $target"
    Write-Host "Expected SHA256: $($hy.sha256)"
    return
}

Ensure-Directory $modelsDir

if ($ModelDir) {
    $source = Join-Path $ModelDir $hy.filename
    if (-not (Test-Path -LiteralPath $source)) {
        $source = Join-Path (Join-Path $ModelDir "models") $hy.filename
    }
    if (-not (Test-Path -LiteralPath $source)) {
        Fail "Offline Hy-MT2 file not found: $source"
    }
    Write-Step "Copying Hy-MT2 from $source"
    Copy-Item -LiteralPath $source -Destination $target -Force
} else {
    $python = Join-Path $PtpRoot "runtime\ptp\python.exe"
    if (-not (Test-Path -LiteralPath $python)) {
        Fail "PTP Python runtime not found: $python"
    }
    $revision = if ($Revision) { $Revision } else { $hy.revision }
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Force
    }
    $env:HF_HUB_DISABLE_XET = "1"
    Write-Step "Downloading Hy-MT2 @ $revision"
    $code = @"
from huggingface_hub import hf_hub_download
import sys
hf_hub_download(
    repo_id=sys.argv[1],
    filename=sys.argv[2],
    revision=sys.argv[3],
    local_dir=sys.argv[4],
)
"@
    & $python -c $code $hy.repo $hy.filename $revision $modelsDir
    if ($LASTEXITCODE -ne 0) {
        Fail "Hy-MT2 download failed."
    }
    Remove-Item -LiteralPath (Join-Path $modelsDir ".cache") -Recurse -Force -ErrorAction SilentlyContinue
}

$actual = Get-Sha256 $target
if ($actual -ne $hy.sha256) {
    Fail "Hy-MT2 SHA256 mismatch. Expected $($hy.sha256), got $actual"
}

Write-ComponentMarker (Join-Path $modelsDir ".ptp-component.json") @{
    name = "hy-model"
    repo = $hy.repo
    revision = $hy.revision
    sha256 = $actual
    path = $target
}
Write-Host "Hy-MT2 installed: $target" -ForegroundColor Green
