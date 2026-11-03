from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from personal_vault.paths import VaultPaths
from personal_vault.config import load_config
from personal_vault.scheduler import (
    install_schedule,
    remove_schedule,
    render_linux_units,
    render_windows_install_script,
)
from personal_vault.setup import initialize


@dataclass
class Result:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


class Runner:
    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], **_: object) -> Result:
        self.calls.append(argv)
        return Result()


def test_linux_units_are_user_scoped_and_run_knowledge_update_only(tmp_path: Path) -> None:
    config = tmp_path / "Private Data" / "config.yaml"
    service, timer = render_linux_units(
        config_path=config,
        python_executable=Path("/opt/personal vault/bin/python"),
        hour=3,
        minute=15,
    )

    assert "personal_vault.cli update" in service
    assert "--apply" in service
    assert "pip install" not in service
    assert "upgrade" not in service.casefold()
    assert "NoNewPrivileges=true" in service
    assert "OnCalendar=*-*-* 03:15:00" in timer
    assert "WantedBy=timers.target" in timer


def test_windows_script_is_native_current_user_and_path_safe() -> None:
    home = PureWindowsPath("C:/") / "Users" / "Alice"
    script = render_windows_install_script(
        config_path=home / "My Data" / "config.yaml",
        python_executable=home / "My Tools" / "python.exe",
        hour=20,
        minute=5,
    )

    assert "New-ScheduledTaskAction" in script
    assert "Register-ScheduledTask" in script
    assert "New-ScheduledTaskTrigger -Daily" in script
    assert "20:05" in script
    assert "personal_vault.cli update" in script
    assert "--apply" in script
    assert "#Requires -RunAsAdministrator" not in script
    assert "wsl" not in script.casefold()
    assert "ubuntu" not in script.casefold()
    assert "upgrade" not in script.casefold()


def test_install_schedule_preview_is_zero_write_then_linux_apply_is_bounded(tmp_path: Path) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="zh-CN")
    unit_dir = tmp_path / "systemd-user"
    runner = Runner()

    preview = install_schedule(
        Path(paths.config),
        os_name="posix",
        apply=False,
        runner=runner,
        unit_dir=unit_dir,
        python_executable=Path("/usr/bin/python3"),
    )
    assert preview["applied"] is False
    assert not unit_dir.exists()

    applied = install_schedule(
        Path(paths.config),
        os_name="posix",
        apply=True,
        runner=runner,
        unit_dir=unit_dir,
        python_executable=Path("/usr/bin/python3"),
    )

    assert (unit_dir / "personal-vault-maintenance.service").is_file()
    assert (unit_dir / "personal-vault-maintenance.timer").is_file()
    assert applied["applied"] is True
    assert load_config(Path(paths.config))["schedule"]["enabled"] is True
    assert runner.calls == [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", "personal-vault-maintenance.timer"],
    ]


def test_windows_install_and_remove_use_powershell_without_admin_escalation(tmp_path: Path) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="en")
    runner = Runner()

    installed = install_schedule(
        Path(paths.config),
        os_name="nt",
        apply=True,
        runner=runner,
        python_executable=Path("C:/Python311/python.exe"),
    )
    removed = remove_schedule(Path(paths.config), os_name="nt", apply=True, runner=runner)

    assert installed["applied"] is True
    assert removed["applied"] is True
    assert all("RunAsAdministrator" not in " ".join(call) for call in runner.calls)
    assert all(call[0].casefold() == "powershell.exe" for call in runner.calls)


def test_remove_linux_schedule_is_reversible_and_user_scoped(tmp_path: Path) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="en")
    unit_dir = tmp_path / "units"
    runner = Runner()
    install_schedule(
        Path(paths.config),
        os_name="posix",
        apply=True,
        runner=runner,
        unit_dir=unit_dir,
        python_executable=Path("/usr/bin/python3"),
    )
    runner.calls.clear()

    result = remove_schedule(
        Path(paths.config),
        os_name="posix",
        apply=True,
        runner=runner,
        unit_dir=unit_dir,
    )

    assert result["applied"] is True
    assert load_config(Path(paths.config))["schedule"]["enabled"] is False
    assert not (unit_dir / "personal-vault-maintenance.service").exists()
    assert runner.calls[0] == ["systemctl", "--user", "disable", "--now", "personal-vault-maintenance.timer"]
