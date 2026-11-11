#requires -Version 7.0
<#
.SYNOPSIS
Create the two release archives from a built portable directory.

.DESCRIPTION
The core archive contains runtimes, tools, TeX, fonts and launchers.  The
models archive contains Hy-MT2 and MinerU models.  Splitting keeps each release
asset below common hosting limits.

.EXAMPLE
pwsh -File scripts/windows/package_archives.ps1
#>
[CmdletBinding()]
param(
    [string]$PortableDir,
    [string]$OutDir,
    [int]$CompressionLevel = 5
)

$ErrorActionPreference = "Stop"
Write-Host "WARNING: legacy monolith packaging. Use build_components.ps1 + package_components.ps1 for component releases." -ForegroundColor Yellow
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $PortableDir) {
    $PortableDir = Join-Path $RepoRoot "build\windows-portable"
}
if (-not $OutDir) {
    $OutDir = Join-Path $RepoRoot "dist"
}
$PortableDir = [System.IO.Path]::GetFullPath($PortableDir)
$OutDir = [System.IO.Path]::GetFullPath($OutDir)

if (-not (Test-Path -LiteralPath (Join-Path $PortableDir "ptp.exe"))) {
    throw "Portable package not found: $PortableDir"
}
if (-not (Get-Command 7z -ErrorAction SilentlyContinue)) {
    throw "7z is required."
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$coreArchive = Join-Path $OutDir "PTP-Windows-x64-core.7z"
$hyModelsArchive = Join-Path $OutDir "PTP-Windows-x64-models-hy.7z"
$mineruModelsArchive = Join-Path $OutDir "PTP-Windows-x64-models-mineru.7z"
foreach ($archive in @($coreArchive, $hyModelsArchive, $mineruModelsArchive)) {
    Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
}

Write-Host "==> core archive" -ForegroundColor Cyan
Push-Location $PortableDir
try {
    7z a -t7z "-mx=$CompressionLevel" $coreArchive "*" `
        "-x!models" "-x!mineru-models" `
        "-x!outputs" "-x!outputs-*" "-x!outputs*" `
        "-x!inputs\*.pdf" `
        "-x!data\outputs*" "-x!data\outputs-*" "-x!data\inputs\*.pdf" "-x!data\*.log"
    if ($LASTEXITCODE -ne 0) {
        throw "7z failed for core archive."
    }
} finally {
    Pop-Location
}

Write-Host "==> Hy-MT2 model archive" -ForegroundColor Cyan
Push-Location $PortableDir
try {
    7z a -t7z "-mx=$CompressionLevel" $hyModelsArchive "models"
    if ($LASTEXITCODE -ne 0) {
        throw "7z failed for Hy-MT2 model archive."
    }
} finally {
    Pop-Location
}

Write-Host "==> MinerU model archive" -ForegroundColor Cyan
Push-Location $PortableDir
try {
    7z a -t7z "-mx=$CompressionLevel" $mineruModelsArchive "mineru-models"
    if ($LASTEXITCODE -ne 0) {
        throw "7z failed for MinerU model archive."
    }
} finally {
    Pop-Location
}

$hashLines = @()
foreach ($file in @($coreArchive, $hyModelsArchive, $mineruModelsArchive)) {
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
Write-Host "Archives and SHA256SUMS.txt written to $OutDir" -ForegroundColor Green
