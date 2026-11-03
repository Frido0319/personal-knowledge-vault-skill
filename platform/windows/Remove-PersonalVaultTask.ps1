[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$TaskName = 'Personal Knowledge Vault Daily Maintenance'
$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $Existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
Write-Output $TaskName

