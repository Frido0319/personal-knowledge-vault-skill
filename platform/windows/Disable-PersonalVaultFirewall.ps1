#Requires -RunAsAdministrator
[CmdletBinding(SupportsShouldProcess = $true)]
param()

$ErrorActionPreference = 'Stop'
$RuleName = 'Personal Knowledge Vault Runtime'
if ($PSCmdlet.ShouldProcess($RuleName, 'Remove runtime firewall rule')) {
    Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction Stop
}

