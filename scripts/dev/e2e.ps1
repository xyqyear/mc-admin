#Requires -Version 7.3
param([string]$Action = 'help')
$ErrorActionPreference = 'Stop'
$PSNativeCommandArgumentPassing = 'Standard'
$distribution = if ($env:MC_ADMIN_WSL_DISTRO) { $env:MC_ADMIN_WSL_DISTRO } else { 'Debian' }
$repository = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$environment = @()
foreach ($name in 'MC_ADMIN_E2E_BINARY', 'MC_ADMIN_E2E_OUTPUT', 'MC_ADMIN_LINUX_VENV') {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ($value) { $environment += "$name=$value" }
}
& wsl.exe --distribution $distribution --cd $repository --exec env @environment bash scripts/dev/e2e.sh $Action @args
exit $LASTEXITCODE
