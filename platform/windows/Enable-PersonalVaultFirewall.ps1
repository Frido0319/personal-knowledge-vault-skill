#Requires -RunAsAdministrator
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$Python
)

$ErrorActionPreference = 'Stop'
$RuleName = 'Personal Knowledge Vault Runtime'
if ($PSCmdlet.ShouldProcess($RuleName, 'Block inbound non-loopback runtime traffic')) {
    Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction Stop
    New-NetFirewallRule `
        -DisplayName $RuleName `
        -Direction Inbound `
        -Program (Resolve-Path -LiteralPath $Python).Path `
        -Action Block `
        -Profile Any | Out-Null
}

