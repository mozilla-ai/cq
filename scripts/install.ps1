<#
.SYNOPSIS
  Wrapper for the cq multi-host installer on Windows.

.DESCRIPTION
  Forwards all arguments to `uv run python -m cq_install` from the
  scripts/install directory. Equivalent to `make install-*` on POSIX.

.EXAMPLE
  .\scripts\install.ps1 install --target cursor --global

.EXAMPLE
  .\scripts\install.ps1 install --target opencode --project C:\src\myapp

.EXAMPLE
  .\scripts\install.ps1 uninstall --target windsurf --global
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$InstallerArgs
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv is required but not found on PATH. Install from https://astral.sh/uv."
    exit 1
}

$installerDir = Join-Path $PSScriptRoot "install"
if (-not (Test-Path $installerDir)) {
    Write-Error "Expected scripts/install directory at: $installerDir"
    exit 1
}

Push-Location $installerDir
try {
    & uv run python -m cq_install @InstallerArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
