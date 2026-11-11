[CmdletBinding()]
param(
    [string]$ModelDir = "",
    [string]$MineruModelDir = "",
    [string]$Wheelhouse = "",
    [string]$Source = "huggingface",
    [switch]$AcceptLicense,
    [switch]$Force,
    [switch]$DryRun
)

. (Join-Path $PSScriptRoot "install-common.ps1")

Write-Step "Installing Hy-MT2 model"
& (Join-Path $PSScriptRoot "install-hy.ps1") `
    -ModelDir $ModelDir -Force:$Force -DryRun:$DryRun

Write-Step "Installing MinerU runtime and models"
& (Join-Path $PSScriptRoot "install-mineru.ps1") `
    -ModelDir $MineruModelDir -Wheelhouse $Wheelhouse -Source $Source `
    -AcceptLicense:$AcceptLicense -Force:$Force -DryRun:$DryRun

Write-Host ""
Write-Host "Component installation finished." -ForegroundColor Green
