<#
Registers the collector as a Windows scheduled task (docs/04-pipelines.md#p1--collector):
starts at boot without anyone signing in, restarts every minute on failure, no time limit.

Run once from an elevated PowerShell (Run as administrator) in the repo root, after `uv sync`
and after creating .env from .env.example:

    powershell -ExecutionPolicy Bypass -File collector\scripts\install-task.ps1

Remove with:  Unregister-ScheduledTask -TaskName airspace-collector -Confirm:$false
#>
#Requires -RunAsAdministrator
param([string]$TaskName = "airspace-collector")
$ErrorActionPreference = "Stop"

$repo = (Resolve-Path "$PSScriptRoot\..\..").Path
$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "No virtualenv: run 'uv sync' in $repo first." }
if (-not (Test-Path (Join-Path $repo ".env"))) { throw "No .env: create $repo\.env from .env.example first." }

# S4U = run whether the user is signed in or not, without storing a password.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited
$action = New-ScheduledTaskAction -Execute $python -Argument "-m collector" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null

# A collector started by hand holds the spool lock; stop it so the task can take over.
# Stopping the venv launcher also stops the Python process it started.
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match [regex]::Escape($python) -and $_.CommandLine -match '-m collector' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Start-ScheduledTask -TaskName $TaskName
Write-Host "Registered and started '$TaskName'."
Write-Host "Check it with:  uv run -m collector status"
Write-Host "Also set Windows to never sleep while plugged in (Settings > System > Power)."
