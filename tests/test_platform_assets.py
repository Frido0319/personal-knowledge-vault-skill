from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_windows_scripts_are_native_parseable_contracts() -> None:
    install = (ROOT / "platform" / "windows" / "Install-PersonalVaultTask.ps1").read_text(encoding="utf-8")
    remove = (ROOT / "platform" / "windows" / "Remove-PersonalVaultTask.ps1").read_text(encoding="utf-8")
    enable = (ROOT / "platform" / "windows" / "Enable-PersonalVaultFirewall.ps1").read_text(encoding="utf-8")
    disable = (ROOT / "platform" / "windows" / "Disable-PersonalVaultFirewall.ps1").read_text(encoding="utf-8")

    assert "Register-ScheduledTask" in install
    assert "Unregister-ScheduledTask" in remove
    assert "#Requires -RunAsAdministrator" not in install
    assert "#Requires -RunAsAdministrator" in enable
    assert "#Requires -RunAsAdministrator" in disable
    assert "Personal Knowledge Vault Runtime" in enable
    assert "Personal Knowledge Vault Runtime" in disable
    assert "New-NetFirewallRule" in enable
    assert "Remove-NetFirewallRule" in disable


def test_linux_templates_do_not_embed_author_machine_paths() -> None:
    service = (ROOT / "platform" / "linux" / "personal-vault-maintenance.service.in").read_text(encoding="utf-8")
    timer = (ROOT / "platform" / "linux" / "personal-vault-maintenance.timer.in").read_text(encoding="utf-8")

    assert "@PYTHON@" in service and "@CONFIG@" in service
    assert "ubuntu20" not in service
    assert "@HOUR@:@MINUTE@" in timer
    assert "--apply" in service
    assert "upgrade" not in service.casefold()
