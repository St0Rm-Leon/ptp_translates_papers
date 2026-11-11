[CmdletBinding()]
param(
    [string]$Wheelhouse = "",
    [string]$ModelDir = "",
    [string]$Source = "huggingface",
    [switch]$AcceptLicense,
    [switch]$Force,
    [switch]$DryRun
)

. (Join-Path $PSScriptRoot "install-common.ps1")

$components = Read-Components
$mineru = $components.mineru
$mineruPython = Join-Path $PtpRoot "runtime\mineru\python.exe"
$mineruKit = Join-Path $PtpRoot "runtime\mineru\Scripts\mineru-kit.exe"
$modelsDir = Join-Path $PtpRoot "mineru-models"
$mineruHome = Join-Path $PtpRoot "data\mineru-home"
$requirements = Join-Path $PSScriptRoot "requirements-mineru.txt"
$licensePath = Join-Path $PtpRoot "LICENSES\MinerU-LICENSE.md"

Confirm-License -Name "MinerU" -LicensePath $licensePath `
    -Url "https://github.com/opendatalab/MinerU/blob/master/LICENSE.md" `
    -AcceptLicense:$AcceptLicense

if (-not (Test-Path -LiteralPath $mineruPython)) {
    Fail "MinerU Python runtime not found: $mineruPython"
}

$hasMineru = $false
& $mineruPython -c "import mineru" 2>$null
if ($LASTEXITCODE -eq 0) {
    $hasMineru = $true
}

$hasModels = (Test-Path -LiteralPath (Join-Path $modelsDir "MinerU-4_models_onnx")) -and `
    (Test-Path -LiteralPath (Join-Path $modelsDir "MinerU2.5-Pro-2605-1.2B-GGUF"))

if ($DryRun) {
    Write-Step "Dry run: MinerU install plan"
    Write-Host "MinerU version: $($mineru.version)"
    Write-Host "Python runtime: $mineruPython"
    Write-Host "MinerU installed: $hasMineru"
    Write-Host "Models present: $hasModels"
    if (-not $hasMineru -or $Force) {
        Write-Host "Would run: pip install -r $requirements"
        if ($Wheelhouse) {
            Write-Host "Offline wheelhouse: $Wheelhouse"
        }
    }
    if ($ModelDir) {
        Write-Host "Would copy models from: $ModelDir"
    } else {
        Write-Host "Would download models from: $Source"
    }
    Write-Host "Would verify with: mineru-kit models verify --tier $($mineru.tier) --small-backend $($mineru.small_backend) --vlm-engine $($mineru.vlm_engine)"
    return
}

Ensure-Directory $modelsDir
Ensure-Directory $mineruHome

if ((-not $hasMineru) -or $Force) {
    Write-Step "Installing MinerU $($mineru.version)"
    $pipArgs = @(
        "-m", "pip", "install", "--break-system-packages",
        "-r", $requirements
    )
    if ($Force) {
        $pipArgs += "--upgrade"
    }
    if ($Wheelhouse) {
        $pipArgs += @("--no-index", "--find-links", $Wheelhouse)
    }
    & $mineruPython @pipArgs
    if ($LASTEXITCODE -ne 0) {
        Fail "MinerU pip install failed."
    }
    & $mineruPython -c "import mineru" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Fail "MinerU import failed after installation."
    }
}

if (-not (Test-Path -LiteralPath $mineruKit)) {
    Fail "mineru-kit not found after installation: $mineruKit"
}

function Write-MineruConfig {
    param([string]$ModelSource)
    $base = $modelsDir.Replace("\", "/")
    $content = @"
model:
  source: $ModelSource
  base_dir: $base
  small_backend: $($mineru.small_backend)
  vlm:
    engine: $($mineru.vlm_engine)
"@
    Set-Content -LiteralPath (Join-Path $mineruHome "config.yaml") -Value $content -Encoding UTF8
}

if ($ModelDir) {
    $sourceDir = $ModelDir
    if (-not (Test-Path -LiteralPath (Join-Path $sourceDir "MinerU-4_models_onnx"))) {
        $nested = Join-Path $ModelDir "mineru-models"
        if (Test-Path -LiteralPath (Join-Path $nested "MinerU-4_models_onnx")) {
            $sourceDir = $nested
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $sourceDir "MinerU-4_models_onnx"))) {
        Fail "Offline MinerU models not found in: $ModelDir"
    }
    Write-Step "Copying MinerU models from $sourceDir"
    Copy-Item -Path (Join-Path $sourceDir "*") -Destination $modelsDir -Recurse -Force
    Write-MineruConfig "local"
} else {
    $env:MINERU_HOME = $mineruHome
    $env:HF_HUB_DISABLE_XET = "1"
    if ($Force -or -not $hasModels) {
        Write-MineruConfig $Source
        Write-Step "Downloading MinerU models from $Source"
        & $mineruKit models download --tier $mineru.tier --small-backend $mineru.small_backend `
            --vlm-engine $mineru.vlm_engine --source $Source
        if ($LASTEXITCODE -ne 0) {
            Fail "MinerU model download failed."
        }
    } else {
        Write-Host "MinerU models already present; skipping download." -ForegroundColor Green
    }
    Write-MineruConfig "local"
}

$env:MINERU_HOME = $mineruHome
Write-Step "Verifying MinerU models"
& $mineruKit models verify --tier $mineru.tier --small-backend $mineru.small_backend `
    --vlm-engine $mineru.vlm_engine
if ($LASTEXITCODE -ne 0) {
    Fail "MinerU model verification failed."
}

Get-ChildItem -LiteralPath $modelsDir -Recurse -Directory -Force -Filter ".cache" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-ComponentMarker (Join-Path $PtpRoot "runtime\mineru\.ptp-component.json") @{
    name = "mineru-runtime"
    version = $mineru.version
    python = $mineruPython
}
Write-ComponentMarker (Join-Path $modelsDir ".ptp-component.json") @{
    name = "mineru-models"
    tier = $mineru.tier
    small_backend = $mineru.small_backend
    vlm_engine = $mineru.vlm_engine
    path = $modelsDir
}
Write-Host "MinerU installed and verified." -ForegroundColor Green
