#requires -Version 7.0
<#
.SYNOPSIS
Create core / hy-model / mineru release archives.

.EXAMPLE
pwsh -File scripts/windows/package_components.ps1 -CompressionLevel 5
#>
[CmdletBinding()]
param(
    [string]$ComponentsDir,
    [string]$OutDir,
    [int]$CompressionLevel = 5
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $ComponentsDir) {
    $ComponentsDir = Join-Path $RepoRoot "build\components"
}
if (-not $OutDir) {
    $OutDir = Join-Path $RepoRoot "dist"
}
$ComponentsDir = [System.IO.Path]::GetFullPath($ComponentsDir)
$OutDir = [System.IO.Path]::GetFullPath($OutDir)

$coreDir = Join-Path $ComponentsDir "core"
$hyDir = Join-Path $ComponentsDir "hy-model"
$mineruDir = Join-Path $ComponentsDir "mineru"
foreach ($dir in @($coreDir, $hyDir, $mineruDir)) {
    if (-not (Test-Path -LiteralPath $dir)) {
        throw "Component directory not found: $dir"
    }
}
if (-not (Get-Command 7z -ErrorAction SilentlyContinue)) {
    throw "7z is required."
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$coreArchive = Join-Path $OutDir "PTP-Windows-x64-core.7z"
$hyArchive = Join-Path $OutDir "PTP-Windows-x64-hy-model.7z"
$mineruArchive = Join-Path $OutDir "PTP-Windows-x64-mineru.7z"
$legacyArchives = @(
    (Join-Path $OutDir "PTP-Windows-x64-models-hy.7z"),
    (Join-Path $OutDir "PTP-Windows-x64-models-mineru.7z"),
    (Join-Path $OutDir "PTP-Windows-x64-models.7z")
)
foreach ($archive in (@($coreArchive, $hyArchive, $mineruArchive) + $legacyArchives)) {
    Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
}

function Write-ComponentArchive([string]$Source, [string]$Archive) {
    Push-Location $Source
    try {
        7z a -t7z "-mx=$CompressionLevel" $Archive "*"
        if ($LASTEXITCODE -ne 0) {
            throw "7z failed for $Archive"
        }
    } finally {
        Pop-Location
    }
}

Write-Host "==> core archive" -ForegroundColor Cyan
Write-ComponentArchive $coreDir $coreArchive

Write-Host "==> hy-model archive" -ForegroundColor Cyan
Write-ComponentArchive $hyDir $hyArchive

Write-Host "==> mineru archive" -ForegroundColor Cyan
Write-ComponentArchive $mineruDir $mineruArchive

$hashLines = @()
foreach ($file in @($coreArchive, $hyArchive, $mineruArchive)) {
    7z t $file | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Archive integrity check failed: $file"
    }
    $hash = Get-FileHash -LiteralPath $file -Algorithm SHA256
    $hashLines += "$($hash.Hash.ToLower())  $([System.IO.Path]::GetFileName($file))"
}
$hashLines | Set-Content -LiteralPath (Join-Path $OutDir "SHA256SUMS.txt") -Encoding ascii

Get-ChildItem -LiteralPath $OutDir -Filter "PTP-Windows-x64-*.7z" |
    Select-Object Name, @{n = "GB"; e = { [math]::Round($_.Length / 1GB, 2) } }
Write-Host "Component archives and SHA256SUMS.txt written to $OutDir" -ForegroundColor Green
