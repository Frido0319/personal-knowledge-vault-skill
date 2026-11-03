from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build(output: Path) -> dict[str, object]:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_release.py"),
            "--output",
            str(output),
            "--allow-dirty",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_release_build_is_reproducible_and_embeds_the_same_wheel(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    one = _build(first)
    two = _build(second)

    assert one["source_commit"] == two["source_commit"]
    first_files = sorted(path.name for path in first.iterdir())
    second_files = sorted(path.name for path in second.iterdir())
    assert first_files == second_files
    assert {_hash(first / name) for name in first_files} == {_hash(second / name) for name in second_files}

    wheel = next(first.glob("*.whl"))
    skill = next(first.glob("*.skill"))
    with zipfile.ZipFile(skill) as archive:
        names = archive.namelist()
        embedded_name = next(name for name in names if name.endswith(".whl"))
        assert archive.read(embedded_name) == wheel.read_bytes()
        sums_name = "build-personal-knowledge-vault/assets/runtime/SHA256SUMS"
        assert _hash(wheel) in archive.read(sums_name).decode("utf-8")
        metadata_name = "build-personal-knowledge-vault/assets/runtime/BUILD-METADATA.json"
        metadata = json.loads(archive.read(metadata_name))
        assert metadata["source_commit"] == one["source_commit"]
        assert metadata["wheel_sha256"] == _hash(wheel)
        assert len({entry.date_time for entry in archive.infolist()}) == 1


def test_release_checksums_cover_exactly_the_release_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "dist"
    report = _build(output)

    lines = (output / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    listed = {line.split(maxsplit=1)[1] for line in lines}
    expected = {next(output.glob("*.whl")).name, next(output.glob("*.skill")).name}

    assert listed == expected
    assert report["artifacts"] == sorted(expected)


def test_built_skill_installs_and_runs_in_a_temporary_home(tmp_path: Path) -> None:
    output = tmp_path / "dist"
    _build(output)
    skill = next(output.glob("*.skill"))
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(skill) as archive:
        archive.extractall(extracted)
    skill_root = extracted / "build-personal-knowledge-vault"
    runtime = tmp_path / "home" / "runtime"
    environment = os.environ.copy()
    environment.update({"HOME": str(tmp_path / "home"), "USERPROFILE": str(tmp_path / "home")})

    installed = subprocess.run(
        [
            sys.executable,
            str(skill_root / "scripts" / "install_runtime.py"),
            "--target",
            str(runtime),
            "--apply",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=180,
    )
    assert installed.returncode == 0, installed.stderr
    install_report = json.loads(installed.stdout)
    assert install_report["applied"] is True

    verified = subprocess.run(
        [
            sys.executable,
            str(skill_root / "scripts" / "verify_install.py"),
            "--target",
            str(runtime),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=120,
    )
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert json.loads(verified.stdout)["ok"] is True
