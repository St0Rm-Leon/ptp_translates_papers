#requires -Version 7.0
<#
.SYNOPSIS
Build the Windows x64 portable PTP package.

.DESCRIPTION
Creates a self-contained directory containing PTP, an isolated MinerU runtime,
Pandoc, TinyTeX, llama.cpp (Vulkan + CPU), Noto CJK fonts and the models.

.EXAMPLE
pwsh -File scripts/windows/build_portable.ps1 `
  -E2EAssets "$env:LOCALAPPDATA\ptp-e2e" `
  -TinyTexDir "$env:LOCALAPPDATA\ptp-e2e\tex-test\TinyTeX"
#>
[CmdletBinding()]
param(
    [string]$OutputDir,
    [string]$PythonDir,
    [string]$PandocExe,
    [string]$LlamaTag = "b12283",
    [string]$TinyTexVersion = "v2026.11",
    [string]$TinyTexDir,
    [string]$E2EAssets,
    [string]$Wheelhouse,
    [switch]$SkipDoctor,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$DefaultOutput = Join-Path $RepoRoot "build\windows-portable"
if (-not $OutputDir) {
    $OutputDir = $DefaultOutput
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)

if (Test-Path -LiteralPath $OutputDir) {
    if (-not $Force -and $OutputDir -ne $DefaultOutput) {
        throw "Output directory already exists: $OutputDir. Pass -Force to replace it."
    }
    Remove-Item -LiteralPath $OutputDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$RuntimeDir = Join-Path $OutputDir "runtime"
$PtPythonDir = Join-Path $RuntimeDir "ptp"
$MineruPythonDir = Join-Path $RuntimeDir "mineru"
$ToolsDir = Join-Path $OutputDir "tools"
$LlamaDir = Join-Path $ToolsDir "llama"
$PandocDir = Join-Path $ToolsDir "pandoc"
$TexDir = Join-Path $OutputDir "tex"
$FontsDir = Join-Path $OutputDir "fonts"
$ModelsDir = Join-Path $OutputDir "models"
$MineruModelsDir = Join-Path $OutputDir "mineru-models"
$InputsDir = Join-Path $OutputDir "inputs"
$OutputsDir = Join-Path $OutputDir "outputs"
$DataDir = Join-Path $OutputDir "data"
$MineruHome = Join-Path $DataDir "mineru-home"
$BuildTemp = Join-Path $OutputDir "_build"

New-Item -ItemType Directory -Force -Path $RuntimeDir, $ToolsDir, $LlamaDir, $PandocDir, $TexDir,
    $FontsDir, $ModelsDir, $MineruModelsDir, $InputsDir, $OutputsDir, $DataDir, $MineruHome,
    $BuildTemp | Out-Null

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
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
        & uv python install 3.13
        $candidates = Get-ChildItem -LiteralPath $managedRoot -Directory |
            Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "python.exe") } |
            Sort-Object Name -Descending
    }
    if (-not $candidates) {
        throw "Could not find a uv-managed CPython 3.13 installation."
    }
    return $candidates[0].FullName
}

function Copy-PythonRuntime([string]$Source, [string]$Destination) {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Copy-Item -Path (Join-Path $Source "*") -Destination $Destination -Recurse -Force
}

function Invoke-Download([string]$Uri, [string]$OutFile) {
    Write-Host "Downloading $Uri"
    Invoke-WebRequest -Uri $Uri -OutFile $OutFile -TimeoutSec 1200
}

function Install-PipPackage([string]$Python, [string]$Spec) {
    $pipArgs = @(
        "pip", "install", "--python", $Python, "--link-mode=copy",
        "--break-system-packages"
    )
    if ($Wheelhouse) {
        $wheelPath = (Resolve-Path -LiteralPath $Wheelhouse).Path
        $pipArgs += @("--no-index", "--find-links", $wheelPath)
    }
    $pipArgs += $Spec
    & uv @pipArgs
    if ($LASTEXITCODE -ne 0) {
        throw "uv pip install failed for $Spec"
    }
}

function Ensure-LlamaVariant([string]$Name) {
    $target = Join-Path $LlamaDir $Name
    if (Test-Path -LiteralPath (Join-Path $target "llama-server.exe")) {
        return
    }
    if ($E2EAssets) {
        $cached = Join-Path $E2EAssets "tools\llama\$Name"
        if (Test-Path -LiteralPath (Join-Path $cached "llama-server.exe")) {
            New-Item -ItemType Directory -Force -Path $target | Out-Null
            Copy-Item -Path (Join-Path $cached "*") -Destination $target -Recurse -Force
            return
        }
    }

    $zip = Join-Path $BuildTemp "llama-$Name.zip"
    $url = "https://github.com/ggml-org/llama.cpp/releases/download/$LlamaTag/llama-$LlamaTag-bin-win-$Name-x64.zip"
    Invoke-Download $url $zip
    Expand-Archive -LiteralPath $zip -DestinationPath $target -Force
    Remove-Item -LiteralPath $zip -Force
}

function Ensure-TinyTex {
    $dest = Join-Path $TexDir "TinyTeX"
    if ($TinyTexDir) {
        if (-not (Test-Path -LiteralPath $TinyTexDir)) {
            throw "TinyTeX directory not found: $TinyTexDir"
        }
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        Copy-Item -Path (Join-Path $TinyTexDir "*") -Destination $dest -Recurse -Force
        return
    }

    $exe = Join-Path $BuildTemp "TinyTeX-1-windows-$TinyTexVersion.exe"
    $url = "https://github.com/rstudio/tinytex-releases/releases/download/$TinyTexVersion/TinyTeX-1-windows-$TinyTexVersion.exe"
    Invoke-Download $url $exe
    7z x $exe "-o$TexDir" -y | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not extract TinyTeX."
    }

    $bin = Join-Path $dest "bin\windows"
    $env:PATH = "$bin;$env:PATH"
    & (Join-Path $bin "tlmgr.bat") update --self
    & (Join-Path $bin "tlmgr.bat") install ctex paracol xecjk multirow caption setspace microtype
    if ($LASTEXITCODE -ne 0) {
        throw "tlmgr install failed."
    }
}

function Assert-TinyTexPackages {
    $bin = Join-Path $TexDir "TinyTeX\bin\windows"
    $kpsewhich = Join-Path $bin "kpsewhich.exe"
    $packages = @(
        "ctexhook.sty", "paracol.sty", "fontspec.sty", "xeCJK.sty", "booktabs.sty",
        "longtable.sty", "multirow.sty", "caption.sty", "hyperref.sty", "amsmath.sty",
        "amssymb.sty", "setspace.sty", "graphicx.sty", "calc.sty", "geometry.sty",
        "etoolbox.sty", "microtype.sty"
    )
    foreach ($package in $packages) {
        $found = & $kpsewhich $package 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $found) {
            throw "TinyTeX is missing required package/file: $package"
        }
    }
}

function Ensure-Fonts {
    $regular = Join-Path $FontsDir "NotoSerifCJKsc-Regular.otf"
    $bold = Join-Path $FontsDir "NotoSerifCJKsc-Bold.otf"
    if ((Test-Path -LiteralPath $regular) -and (Test-Path -LiteralPath $bold)) {
        return
    }
    if ($E2EAssets -and (Test-Path -LiteralPath (Join-Path $E2EAssets "fonts\NotoSerifCJKsc-Regular.otf"))) {
        Copy-Item -Path (Join-Path $E2EAssets "fonts\*") -Destination $FontsDir -Force
        return
    }
    Invoke-Download "https://github.com/notofonts/noto-cjk/raw/main/Serif/OTF/SimplifiedChinese/NotoSerifCJKsc-Regular.otf" $regular
    Invoke-Download "https://github.com/notofonts/noto-cjk/raw/main/Serif/OTF/SimplifiedChinese/NotoSerifCJKsc-Bold.otf" $bold
}

function Ensure-TranslationModel {
    $model = Join-Path $ModelsDir "Hy-MT2-1.8B-Q4_K_M.gguf"
    if (-not (Test-Path -LiteralPath $model)) {
        if ($E2EAssets -and (Test-Path -LiteralPath (Join-Path $E2EAssets "models\Hy-MT2-1.8B-Q4_K_M.gguf"))) {
            Copy-Item -LiteralPath (Join-Path $E2EAssets "models\Hy-MT2-1.8B-Q4_K_M.gguf") -Destination $model
        } else {
            $env:HF_HUB_DISABLE_XET = "1"
            & $script:PtPython -c "from huggingface_hub import hf_hub_download; import sys; hf_hub_download(repo_id='tencent/Hy-MT2-1.8B-GGUF', filename='Hy-MT2-1.8B-Q4_K_M.gguf', local_dir=sys.argv[1])" $ModelsDir
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $model)) {
                throw "Could not download Hy-MT2."
            }
        }
    }

    Remove-Item -LiteralPath (Join-Path $ModelsDir ".cache") -Recurse -Force -ErrorAction SilentlyContinue
    Set-Content -LiteralPath (Join-Path $ModelsDir "README.txt") -Encoding utf8 -Value @"
Hy-MT2-1.8B Q4_K_M GGUF for PTP.

Source: https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF
License: Apache-2.0 (see THIRD_PARTY_NOTICES.md and the upstream model card).

This model is not part of PTP's GPL license.
"@
}

function Write-MineruConfig([string]$Source) {
    $base = $MineruModelsDir.Replace("\", "/")
    $content = @"
model:
  source: $Source
  base_dir: $base
  small_backend: onnx
  vlm:
    engine: llama-cpp
"@
    Set-Content -LiteralPath (Join-Path $MineruHome "config.yaml") -Value $content -Encoding utf8
}

function Ensure-MineruModels {
    $mineruKit = Join-Path $MineruPythonDir "Scripts\mineru-kit.exe"
    $env:MINERU_HOME = $MineruHome
    $env:HF_HUB_DISABLE_XET = "1"

    if ($E2EAssets -and (Test-Path -LiteralPath (Join-Path $E2EAssets "mineru-models"))) {
        Copy-Item -Path (Join-Path $E2EAssets "mineru-models\*") -Destination $MineruModelsDir -Recurse -Force
        Write-MineruConfig "local"
    } else {
        Write-MineruConfig "huggingface"
        & $mineruKit models download --tier standard --small-backend onnx --vlm-engine llama-cpp --source huggingface
        if ($LASTEXITCODE -ne 0) {
            throw "MinerU model download failed."
        }
        Write-MineruConfig "local"
    }

    & $mineruKit models verify --tier standard --small-backend onnx --vlm-engine llama-cpp
    if ($LASTEXITCODE -ne 0) {
        throw "MinerU model verification failed."
    }

    Get-ChildItem -LiteralPath $MineruModelsDir -Recurse -Directory -Force -Filter ".cache" -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Set-Content -LiteralPath (Join-Path $MineruModelsDir "README.txt") -Encoding utf8 -Value @"
MinerU models for PTP.

Source:
  https://huggingface.co/opendatalab/MinerU-4_models_onnx
  https://huggingface.co/opendatalab/MinerU2.5-Pro-2605-1.2B-GGUF

These files are not part of PTP's GPL license.  Preserve the upstream model
cards and licenses when redistributing this directory.
"@
}

function Write-Config {
    $content = @"
version: 1

input: inputs
output: outputs
keep_temp: true
resume: false
threads: auto
parallel: 1

device: auto
gpu_backend: auto
gpu_index: null

mineru:
  tier: auto
  python: runtime/mineru/python.exe
  model_source: local
  model_dir: mineru-models
  home: data/mineru-home

translation:
  model: models/Hy-MT2-1.8B-Q4_K_M.gguf
  server_bin: tools/llama/vulkan/llama-server.exe
  llama_cli: tools/llama/vulkan/llama-cli.exe
  server_url: null
  host: 127.0.0.1
  port: 0
  threads: null
  gpu_layers: auto
  chunk_tokens: 800
  temperature: 0.3
  top_p: 0.6
  top_k: 20
  repetition_penalty: 1.05
  max_tokens: 2048
  timeout: 600
  context_size: 4096

render:
  layout: single
  engine: xelatex
  cjk_font: Noto Serif CJK SC
  cjk_font_file: fonts/NotoSerifCJKsc-Regular.otf
  cjk_font_bold_file: fonts/NotoSerifCJKsc-Bold.otf
  pandoc: tools/pandoc/pandoc.exe
  xelatex: tex/TinyTeX/bin/windows/xelatex.exe
  source_ratio: 0.48
  source_line_spacing: 1.35
  target_line_spacing: 1.15
  figure_max_height: 0.45
"@
    Set-Content -LiteralPath (Join-Path $OutputDir "config.yaml") -Value $content -Encoding utf8
}

function Write-Launcher {
    $csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    if (-not (Test-Path -LiteralPath $csc)) {
        throw "csc.exe (.NET Framework 4.8) not found: $csc"
    }
    $launcherSource = Join-Path $PSScriptRoot "ptp_launcher.cs"
    $manifest = Join-Path $PSScriptRoot "ptp.exe.manifest"
    $buildSource = Join-Path $BuildTemp "ptp_launcher.cs"
    $buildManifest = Join-Path $BuildTemp "ptp.exe.manifest"
    Copy-Item -LiteralPath $launcherSource -Destination $buildSource
    Copy-Item -LiteralPath $manifest -Destination $buildManifest

    & $csc /nologo /target:exe /platform:x64 /optimize+ /codepage:65001 `
        "/win32manifest:$buildManifest" "/out:$(Join-Path $OutputDir 'ptp.exe')" `
        /r:System.dll $buildSource
    if ($LASTEXITCODE -ne 0) {
        throw "Could not compile ptp.exe."
    }

    $cmd = @"
@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "MINERU_HOME=%~dp0data\mineru-home"
set "HF_HOME=%~dp0data\hf-cache"
"%~dp0runtime\ptp\python.exe" -m ptp %*
"@
    Set-Content -LiteralPath (Join-Path $OutputDir "ptp.cmd") -Value $cmd -Encoding ascii
}

function Copy-Notices {
    Copy-Item -LiteralPath (Join-Path $RepoRoot "LICENSE") -Destination $OutputDir
    Copy-Item -LiteralPath (Join-Path $RepoRoot "THIRD_PARTY_NOTICES.md") -Destination $OutputDir
    Copy-Item -LiteralPath (Join-Path $RepoRoot "LICENSES") -Destination $OutputDir -Recurse
    Copy-Item -LiteralPath (Join-Path $RepoRoot "docs\windows.md") -Destination (Join-Path $OutputDir "README-Windows.md")

    Copy-Item -LiteralPath (Join-Path $PtPythonDir "LICENSE.txt") -Destination (Join-Path $OutputDir "LICENSES\Python-PSF-2.0.txt")
    Copy-Item -LiteralPath (Join-Path $RepoRoot "LICENSE") -Destination (Join-Path $OutputDir "LICENSES\GPL-2.0-or-later.txt")
    Copy-Item -LiteralPath (Join-Path $TexDir "TinyTeX\LICENSE.TL") -Destination (Join-Path $OutputDir "LICENSES\TinyTeX-LICENSE.TL")
    Copy-Item -LiteralPath (Join-Path $TexDir "TinyTeX\LICENSE.CTAN") -Destination (Join-Path $OutputDir "LICENSES\TinyTeX-LICENSE.CTAN")
}

function Write-Manifest {
    $pandocVersion = (& (Join-Path $PandocDir "pandoc.exe") --version | Select-Object -First 1)
    $xelatexVersion = (& (Join-Path $TexDir "TinyTeX\bin\windows\xelatex.exe") --version | Select-Object -First 1)
    $manifest = [ordered]@{
        built_at = (Get-Date).ToString("o")
        platform = "windows-x64"
        python = (& $script:PtPython --version)
        mineru = "4.1.x"
        llama_cpp = $LlamaTag
        pandoc = "$pandocVersion"
        tinytex = $TinyTexVersion
        xelatex = "$xelatexVersion"
    }
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $OutputDir "build-manifest.json") -Encoding utf8
}

Write-Step "Preparing Python runtimes"
$pythonSource = Get-PythonSource
Copy-PythonRuntime $pythonSource $PtPythonDir
Copy-PythonRuntime $pythonSource $MineruPythonDir
$script:PtPython = Join-Path $PtPythonDir "python.exe"
$mineruPython = Join-Path $MineruPythonDir "python.exe"

Write-Step "Building and installing PTP"
Push-Location $RepoRoot
try {
    & uv build
    if ($LASTEXITCODE -ne 0) {
        throw "uv build failed."
    }
} finally {
    Pop-Location
}
$wheel = Get-ChildItem -LiteralPath (Join-Path $RepoRoot "dist") -Filter "ptp_translates_papers-*.whl" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $wheel) {
    throw "PTP wheel not found."
}
Install-PipPackage $script:PtPython $wheel.FullName

Write-Step "Installing MinerU 4.1 into its own runtime"
Install-PipPackage $mineruPython "mineru>=4.1,<4.2"

Write-Step "Bundling Pandoc"
if (-not $PandocExe) {
    $pandocCommand = Get-Command pandoc -ErrorAction SilentlyContinue
    if ($pandocCommand) {
        $PandocExe = $pandocCommand.Source
    }
    if (Get-Command scoop -ErrorAction SilentlyContinue) {
        $prefix = (& scoop prefix pandoc 2>$null)
        if ($prefix -and (Test-Path -LiteralPath (Join-Path $prefix "pandoc.exe"))) {
            $PandocExe = Join-Path $prefix "pandoc.exe"
        }
    }
}
if (-not $PandocExe -or -not (Test-Path -LiteralPath $PandocExe)) {
    throw "Pandoc not found. Pass -PandocExe."
}
Copy-Item -LiteralPath $PandocExe -Destination (Join-Path $PandocDir "pandoc.exe")

Write-Step "Bundling llama.cpp $LlamaTag"
Ensure-LlamaVariant "vulkan"
Ensure-LlamaVariant "cpu"

Write-Step "Bundling TinyTeX"
Ensure-TinyTex
Assert-TinyTexPackages

Write-Step "Bundling fonts"
Ensure-Fonts

Write-Step "Bundling models"
Ensure-TranslationModel
Ensure-MineruModels

Write-Step "Writing configuration, launcher and notices"
Write-Config
Write-Launcher
Copy-Notices
Write-Manifest

New-Item -ItemType Directory -Force -Path $InputsDir, $OutputsDir,
    (Join-Path $DataDir "hf-cache"), (Join-Path $DataDir "logs") | Out-Null
Set-Content -LiteralPath (Join-Path $InputsDir "README.txt") -Encoding utf8 -Value @"
Put English paper PDFs in this directory, or pass them with -i.

Example:
  .\ptp.exe -i inputs\paper.pdf -o outputs
"@
Remove-Item -LiteralPath $BuildTemp -Recurse -Force

if (-not $SkipDoctor) {
    Write-Step "Running portable ptp.exe --doctor"
    & (Join-Path $OutputDir "ptp.exe") --doctor
    if ($LASTEXITCODE -ne 0) {
        throw "Portable package doctor check failed."
    }
}

Write-Step "Portable package ready: $OutputDir"
