from __future__ import annotations

import os
from pathlib import Path, PurePath, PureWindowsPath
import subprocess
import sys
from typing import Any, Callable

from .config import load_config, write_config_atomic
from .proposals import _atomic_text


SERVICE_NAME = "personal-vault-maintenance.service"
TIMER_NAME = "personal-vault-maintenance.timer"
WINDOWS_TASK_NAME = "Personal Knowledge Vault Daily Maintenance"


class SchedulerError(RuntimeError):
    """Raised when a platform scheduler operation fails."""


Runner = Callable[..., Any]


def _set_schedule_enabled(config_file: Path, config: dict[str, Any], enabled: bool) -> None:
    schedule = config.get("schedule")
    if not isinstance(schedule, dict):
        schedule = {"hour": 3, "minute": 15}
        config["schedule"] = schedule
    schedule["enabled"] = enabled
    write_config_atomic(config_file, config)


def _systemd_quote(value: PurePath) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return f'"{escaped}"'


def render_linux_units(
    *,
    config_path: PurePath,
    python_executable: PurePath,
    hour: int,
    minute: int,
) -> tuple[str, str]:
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise SchedulerError("SCHEDULE_TIME_INVALID")
    service = f"""[Unit]
Description=Personal Knowledge Vault deterministic maintenance
After=local-fs.target

[Service]
Type=oneshot
ExecStart={_systemd_quote(python_executable)} -m personal_vault.cli update --config {_systemd_quote(config_path)} --apply
NoNewPrivileges=true
PrivateTmp=true
ProtectControlGroups=true
ProtectKernelModules=true
ProtectKernelTunables=true
RestrictSUIDSGID=true

[Install]
WantedBy=default.target
"""
    timer = f"""[Unit]
Description=Run Personal Knowledge Vault maintenance daily

[Timer]
OnCalendar=*-*-* {hour:02d}:{minute:02d}:00
Persistent=true
RandomizedDelaySec=10m
Unit={SERVICE_NAME}

[Install]
WantedBy=timers.target
"""
    return service, timer


def _ps_literal(value: PurePath | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def render_windows_install_script(
    *,
    config_path: PurePath,
    python_executable: PurePath,
    hour: int,
    minute: int,
) -> str:
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise SchedulerError("SCHEDULE_TIME_INVALID")
    return f"""$ErrorActionPreference = 'Stop'
$TaskName = {_ps_literal(WINDOWS_TASK_NAME)}
$Python = {_ps_literal(python_executable)}
$Config = {_ps_literal(config_path)}
$Arguments = '-m personal_vault.cli update --config "' + $Config + '" --apply'
$Action = New-ScheduledTaskAction -Execute $Python -Argument $Arguments
$Trigger = New-ScheduledTaskTrigger -Daily -At '{hour:02d}:{minute:02d}'
$Principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description 'Personal Knowledge Vault deterministic maintenance' -Force | Out-Null
Write-Output $TaskName
"""


def _windows_remove_script() -> str:
    return f"""$ErrorActionPreference = 'Stop'
$TaskName = {_ps_literal(WINDOWS_TASK_NAME)}
$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $Existing) {{
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}}
Write-Output $TaskName
"""


def _checked(runner: Runner, argv: list[str]) -> None:
    result = runner(argv, check=False, capture_output=True, text=True)
    if int(getattr(result, "returncode", 1)) != 0:
        raise SchedulerError("SCHEDULER_COMMAND_FAILED")


def install_schedule(
    config_path: str | Path,
    *,
    os_name: str | None = None,
    apply: bool = False,
    runner: Runner = subprocess.run,
    unit_dir: str | Path | None = None,
    python_executable: PurePath | None = None,
) -> dict[str, Any]:
    config_file = Path(config_path).expanduser().resolve(strict=False)
    config = load_config(config_file)
    schedule = config.get("schedule", {})
    hour = int(schedule.get("hour", 3)) if isinstance(schedule, dict) else 3
    minute = int(schedule.get("minute", 15)) if isinstance(schedule, dict) else 15
    platform_name = os_name or os.name
    executable = python_executable or Path(sys.executable)
    if platform_name == "nt":
        script = render_windows_install_script(
            config_path=PureWindowsPath(str(config_file)),
            python_executable=PureWindowsPath(str(executable)),
            hour=hour,
            minute=minute,
        )
        target = Path(str(config["data"])).expanduser() / "runtime" / "scheduler" / "Install-PersonalVaultTask.ps1"
        result = {"applied": False, "platform": "windows", "task": WINDOWS_TASK_NAME, "files": [str(target)], "script": script}
        if not apply:
            return result
        _atomic_text(target, script)
        _checked(runner, ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(target)])
        _set_schedule_enabled(config_file, config, True)
        result["applied"] = True
        return result
    if platform_name != "posix":
        raise SchedulerError("PLATFORM_NOT_SUPPORTED")
    service, timer = render_linux_units(
        config_path=config_file,
        python_executable=Path(executable),
        hour=hour,
        minute=minute,
    )
    target_root = Path(unit_dir).expanduser() if unit_dir is not None else Path.home() / ".config" / "systemd" / "user"
    service_path = target_root / SERVICE_NAME
    timer_path = target_root / TIMER_NAME
    result = {
        "applied": False,
        "platform": "linux",
        "unit": TIMER_NAME,
        "files": [str(service_path), str(timer_path)],
        "service": service,
        "timer": timer,
    }
    if not apply:
        return result
    _atomic_text(service_path, service)
    _atomic_text(timer_path, timer)
    _checked(runner, ["systemctl", "--user", "daemon-reload"])
    _checked(runner, ["systemctl", "--user", "enable", "--now", TIMER_NAME])
    _set_schedule_enabled(config_file, config, True)
    result["applied"] = True
    return result


def remove_schedule(
    config_path: str | Path,
    *,
    os_name: str | None = None,
    apply: bool = False,
    runner: Runner = subprocess.run,
    unit_dir: str | Path | None = None,
) -> dict[str, Any]:
    config_file = Path(config_path).expanduser().resolve(strict=False)
    config = load_config(config_file)
    platform_name = os_name or os.name
    if platform_name == "nt":
        target = Path(str(config["data"])).expanduser() / "runtime" / "scheduler" / "Remove-PersonalVaultTask.ps1"
        script = _windows_remove_script()
        result = {"applied": False, "platform": "windows", "task": WINDOWS_TASK_NAME, "files": [str(target)], "script": script}
        if not apply:
            return result
        _atomic_text(target, script)
        _checked(runner, ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(target)])
        _set_schedule_enabled(config_file, config, False)
        result["applied"] = True
        return result
    if platform_name != "posix":
        raise SchedulerError("PLATFORM_NOT_SUPPORTED")
    target_root = Path(unit_dir).expanduser() if unit_dir is not None else Path.home() / ".config" / "systemd" / "user"
    files = [target_root / SERVICE_NAME, target_root / TIMER_NAME]
    result = {"applied": False, "platform": "linux", "unit": TIMER_NAME, "files": [str(path) for path in files]}
    if not apply:
        return result
    _checked(runner, ["systemctl", "--user", "disable", "--now", TIMER_NAME])
    for path in files:
        path.unlink(missing_ok=True)
    _checked(runner, ["systemctl", "--user", "daemon-reload"])
    _set_schedule_enabled(config_file, config, False)
    result["applied"] = True
    return result
