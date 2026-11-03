[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Python,
    [Parameter(Mandatory = $true)]
    [string]$Config,
    [ValidateRange(0, 23)]
    [int]$Hour = 3,
    [ValidateRange(0, 59)]
    [int]$Minute = 15
)

$ErrorActionPreference = 'Stop'
$TaskName = 'Personal Knowledge Vault Daily Maintenance'
$Arguments = '-m personal_vault.cli update --config "' + $Config + '" --apply'
$Action = New-ScheduledTaskAction -Execute $Python -Argument $Arguments
$Trigger = New-ScheduledTaskTrigger -Daily -At ('{0:D2}:{1:D2}' -f $Hour, $Minute)
$Principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Description 'Personal Knowledge Vault deterministic maintenance' `
    -Force | Out-Null

Write-Output $TaskName

