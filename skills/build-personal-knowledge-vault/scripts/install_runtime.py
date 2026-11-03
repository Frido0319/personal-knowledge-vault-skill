#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv


class InstallerError(RuntimeError):
    pass


def _default_target() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "PersonalVault" / "runtime"
    return Path.home() / ".local" / "share" / "personal-vault" / "runtime"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expected_hashes(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise InstallerError("SHA256SUMS_READ_FAILED") from exc
    expected: dict[str, str] = {}
    for line in lines:
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise InstallerError("SHA256SUMS_INVALID")
        name = parts[1].strip().lstrip("*")
        if Path(name).name != name:
            raise InstallerError("SHA256SUMS_PATH_INVALID")
        expected[name] = parts[0].casefold()
    return expected


def verify_bundled_wheel(skill_root: Path) -> tuple[Path, str]:
    runtime = skill_root.resolve() / "assets" / "runtime"
    wheels = sorted(runtime.glob("personal_knowledge_vault-*.whl"))
    if len(wheels) != 1:
        raise InstallerError("ONE_BUNDLED_RUNTIME_WHEEL_REQUIRED")
    wheel = wheels[0]
    expected = _expected_hashes(runtime / "SHA256SUMS").get(wheel.name)
    if expected is None:
        raise InstallerError("WHEEL_HASH_NOT_LISTED")
    actual = _sha256(wheel)
    if not hmac.compare_digest(expected, actual):
        raise InstallerError("WHEEL_HASH_MISMATCH")
    return wheel, actual


def _venv_python(target: Path) -> Path:
    return target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, capture_output=True, text=True, timeout=300)


def install_runtime(
    *,
    skill_root: Path,
    target: Path,
    apply: bool,
    allow_network: bool,
) -> dict[str, object]:
    wheel, digest = verify_bundled_wheel(skill_root)
    target = target.expanduser().resolve(strict=False)
    result: dict[str, object] = {
        "applied": False,
        "target": str(target),
        "wheel": wheel.name,
        "sha256": digest,
        "network_allowed": allow_network,
    }
    if not apply:
        return result
    if target.exists():
        raise InstallerError("TARGET_EXISTS_USE_SEPARATE_UPGRADE_ENVIRONMENT")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        venv.EnvBuilder(with_pip=True, system_site_packages=not allow_network).create(target)
        python = _venv_python(target)
        command = [str(python), "-m", "pip", "install", "--disable-pip-version-check"]
        if not allow_network:
            command.append("--no-deps")
        command.append(str(wheel))
        installed = _run(command)
        if installed.returncode != 0:
            raise InstallerError("BUNDLED_WHEEL_INSTALL_FAILED")
        verified = _run([str(python), "-c", "import personal_vault, yaml"])
        if verified.returncode != 0:
            code = "DEPENDENCY_NETWORK_CONSENT_REQUIRED" if not allow_network else "RUNTIME_IMPORT_FAILED"
            raise InstallerError(code)
        receipt = {
            "schema_version": 1,
            "wheel": wheel.name,
            "sha256": digest,
            "network_allowed": allow_network,
        }
        (target / "personal-vault-install.json").write_text(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    result["applied"] = True
    result["python"] = str(_venv_python(target))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install the hash-verified runtime bundled with this Skill.")
    parser.add_argument("--target", type=Path, default=_default_target())
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow pip to resolve missing dependencies from its configured package index.",
    )
    arguments = parser.parse_args(argv)
    try:
        result = install_runtime(
            skill_root=Path(__file__).resolve().parents[1],
            target=arguments.target,
            apply=arguments.apply,
            allow_network=arguments.allow_network,
        )
    except (InstallerError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
