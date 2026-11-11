#requires -Version 7.0
<#
.SYNOPSIS
Smoke-test a built Windows portable PTP package.

.EXAMPLE
pwsh -File scripts/windows/verify_portable.ps1

.EXAMPLE
pwsh -File scripts/windows/verify_portable.ps1 -Pdf F:\papers\paper.pdf -RunFlash
#>
[CmdletBinding()]
param(
    [string]$PortableDir,
    [string]$Pdf,
    [switch]$RunFlash
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $PortableDir) {
    $PortableDir = Join-Path $RepoRoot "build\windows-portable"
}
$PortableDir = [System.IO.Path]::GetFullPath($PortableDir)
$exe = Join-Path $PortableDir "ptp.exe"

if (-not (Test-Path -LiteralPath $exe)) {
    throw "Portable launcher not found: $exe"
}

Write-Host "==> ptp.exe --doctor" -ForegroundColor Cyan
& $exe --doctor
if ($LASTEXITCODE -ne 0) {
    throw "Doctor check failed."
}

$dryRunArgs = @("--dry-run", "--device", "cpu")
if ($Pdf) {
    $dryRunArgs += @("-i", $Pdf)
} elseif (Test-Path -LiteralPath (Join-Path $RepoRoot "inputs\nci195.pdf")) {
    $dryRunArgs += @("-i", (Join-Path $RepoRoot "inputs\nci195.pdf"))
}
Write-Host "==> ptp.exe --dry-run" -ForegroundColor Cyan
& $exe @dryRunArgs
if ($LASTEXITCODE -ne 0) {
    throw "Dry-run failed."
}

if ($RunFlash) {
    if (-not $Pdf) {
        $Pdf = Join-Path $RepoRoot "inputs\nci195.pdf"
    }
    if (-not (Test-Path -LiteralPath $Pdf)) {
        throw "PDF not found for flash smoke test: $Pdf"
    }
    $out = Join-Path $PortableDir "outputs-smoke"
    Write-Host "==> ptp.exe --tier flash" -ForegroundColor Cyan
    & $exe -i $Pdf -o $out --device cpu --tier flash
    if ($LASTEXITCODE -ne 0) {
        throw "Flash smoke test failed."
    }
    Write-Host "Smoke output: $out"
}

Write-Host "Portable smoke test passed." -ForegroundColor Green
