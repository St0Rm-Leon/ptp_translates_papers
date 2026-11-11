#requires -Version 7.0
<#
.SYNOPSIS
Split a built full portable package into core / hy-model / mineru components.

.DESCRIPTION
The resulting directories can be archived separately.  The core component
contains an empty MinerU Python runtime; install-mineru.ps1 installs the
MinerU packages into it.

.EXAMPLE
pwsh -File scripts/windows/build_components.ps1 `
  -SourceDir build\windows-portable
#>
[CmdletBinding()]
param(
    [string]$SourceDir,
    [string]$OutputDir,
    [string]$PythonDir,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $SourceDir) {
    $SourceDir = Join-Path $RepoRoot "build\windows-portable"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $RepoRoot "build\components"
}
$SourceDir = [System.IO.Path]::GetFullPath($SourceDir)
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)

$required = @("ptp.exe", "runtime\ptp", "runtime\mineru", "tools", "tex", "fonts", "models", "mineru-models")
foreach ($item in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $SourceDir $item))) {
        throw "Source package is missing $item"
    }
}

if (Test-Path -LiteralPath $OutputDir) {
    if (-not $Force) {
        throw "Output directory already exists: $OutputDir. Pass -Force to replace it."
    }
    Remove-Item -LiteralPath $OutputDir -Recurse -Force
}
$CoreDir = Join-Path $OutputDir "core"
$HyDir = Join-Path $OutputDir "hy-model"
$MineruDir = Join-Path $OutputDir "mineru"
New-Item -ItemType Directory -Force -Path $CoreDir, $HyDir, $MineruDir | Out-Null

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Copy-Directory([string]$Source, [string]$Destination) {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Copy-Item -Path (Join-Path $Source "*") -Destination $Destination -Recurse -Force
}

function Get-PythonSource {
    if ($PythonDir) {
        if (-not (Test-Path -LiteralPath $PythonDir)) {
            throw "Python directory not found: $PythonDir"
        }
        return (Resolve-Path -LiteralPath $PythonDir).Path
    }
    $managedRoot = (& uv python dir).Trim()
    $candidates = Get-ChildItem -LiteralPath $managedRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "python.exe") } |
        Sort-Object Name -Descending
    if (-not $candidates) {
        throw "No uv-managed Python found. Pass -PythonDir."
    }
    return $candidates[0].FullName
}

Write-Step "Building core component"
$coreRuntime = Join-Path $CoreDir "runtime"
New-Item -ItemType Directory -Force -Path $coreRuntime | Out-Null
Copy-Directory (Join-Path $SourceDir "runtime\ptp") (Join-Path $coreRuntime "ptp")

$emptyPython = Get-PythonSource
Copy-Directory $emptyPython (Join-Path $coreRuntime "mineru")
& (Join-Path $coreRuntime "mineru\python.exe") -m pip --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The empty MinerU runtime does not provide pip."
}
Set-Content -LiteralPath (Join-Path $coreRuntime "mineru\README.txt") -Encoding utf8 -Value @"
This directory is the MinerU Python runtime.

If MinerU is not installed yet, run install-mineru.cmd from the package root.
In the full version, MinerU packages and models are already installed.
"@

foreach ($dir in @("tools", "tex", "fonts", "LICENSES")) {
    Copy-Directory (Join-Path $SourceDir $dir) (Join-Path $CoreDir $dir)
}
foreach ($file in @("ptp.exe", "ptp.cmd", "config.yaml", "build-manifest.json")) {
    Copy-Item -LiteralPath (Join-Path $SourceDir $file) -Destination $CoreDir
}
Copy-Item -LiteralPath (Join-Path $RepoRoot "LICENSE") -Destination $CoreDir
Copy-Item -LiteralPath (Join-Path $RepoRoot "THIRD_PARTY_NOTICES.md") -Destination $CoreDir
Copy-Item -LiteralPath (Join-Path $RepoRoot "docs\windows.md") -Destination (Join-Path $CoreDir "README-Windows.md")

New-Item -ItemType Directory -Force -Path `
    (Join-Path $CoreDir "inputs"), (Join-Path $CoreDir "outputs"), `
    (Join-Path $CoreDir "data\hf-cache"), (Join-Path $CoreDir "data\logs"), `
    (Join-Path $CoreDir "data\mineru-home"), (Join-Path $CoreDir "install") | Out-Null
Set-Content -LiteralPath (Join-Path $CoreDir "inputs\README.txt") -Encoding utf8 -Value @"
Put English paper PDFs in this directory, or pass them with -i.

Example:
  .\ptp.exe -i inputs\paper.pdf -o outputs
"@

$installSource = Join-Path $PSScriptRoot "install"
Copy-Item -LiteralPath (Join-Path $installSource "install-common.ps1") -Destination (Join-Path $CoreDir "install")
Copy-Item -LiteralPath (Join-Path $installSource "install-hy.ps1") -Destination (Join-Path $CoreDir "install")
Copy-Item -LiteralPath (Join-Path $installSource "install-mineru.ps1") -Destination (Join-Path $CoreDir "install")
Copy-Item -LiteralPath (Join-Path $installSource "install-all.ps1") -Destination (Join-Path $CoreDir "install")
Copy-Item -LiteralPath (Join-Path $installSource "requirements-mineru.txt") -Destination (Join-Path $CoreDir "install")
Copy-Item -LiteralPath (Join-Path $installSource "components.example.json") -Destination (Join-Path $CoreDir "components.json")

foreach ($wrapper in @("install-hy.cmd", "install-mineru.cmd", "install-all.cmd")) {
    Copy-Item -LiteralPath (Join-Path $installSource $wrapper) -Destination $CoreDir
}

$manifest = Get-Content -LiteralPath (Join-Path $CoreDir "components.json") -Raw | ConvertFrom-Json
$manifest.core.python = (& (Join-Path $coreRuntime "mineru\python.exe") -c "import platform; print(platform.python_version())").Trim()
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $CoreDir "components.json") -Encoding utf8

Write-Step "Building hy-model component"
$hyModels = Join-Path $HyDir "models"
New-Item -ItemType Directory -Force -Path $hyModels | Out-Null
Copy-Item -LiteralPath (Join-Path $SourceDir "models\Hy-MT2-1.8B-Q4_K_M.gguf") -Destination $hyModels
if (Test-Path -LiteralPath (Join-Path $SourceDir "models\README.txt")) {
    Copy-Item -LiteralPath (Join-Path $SourceDir "models\README.txt") -Destination $hyModels
}

Write-Step "Building mineru component"
Copy-Directory (Join-Path $SourceDir "runtime\mineru") (Join-Path $MineruDir "runtime\mineru")
Copy-Directory (Join-Path $SourceDir "mineru-models") (Join-Path $MineruDir "mineru-models")

Write-Step "Components ready: $OutputDir"
Get-ChildItem -LiteralPath $OutputDir | Select-Object Name
