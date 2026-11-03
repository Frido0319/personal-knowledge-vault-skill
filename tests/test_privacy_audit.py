from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "privacy_audit.py"


def _audit(root: Path) -> tuple[int, dict[str, object]]:
    result = subprocess.run(
        [sys.executable, str(AUDIT), "--root", str(root)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode, json.loads(result.stdout)


def test_public_repository_passes_privacy_audit() -> None:
    code, report = _audit(ROOT)

    assert code == 0, report
    assert report["ok"] is True
    assert report["findings"] == []


def test_privacy_audit_rejects_private_paths_and_secrets(tmp_path: Path) -> None:
    private_path = "/" + "home/alice/PersonalVault"
    token = "gh" + "p_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890ab"
    (tmp_path / "README.md").write_text(
        f"private={private_path}\ntoken={token}\n",
        encoding="utf-8",
    )

    code, report = _audit(tmp_path)
    finding_codes = {finding["code"] for finding in report["findings"]}

    assert code == 1
    assert "PRIVATE_ABSOLUTE_PATH" in finding_codes
    assert "SECRET_PATTERN" in finding_codes


def test_privacy_audit_rejects_symlinks_and_credential_filenames(tmp_path: Path) -> None:
    target = tmp_path / "plain.txt"
    target.write_text("safe", encoding="utf-8")
    os.symlink(target, tmp_path / "linked.txt")
    (tmp_path / ".env").write_text("MODE=test\n", encoding="utf-8")

    code, report = _audit(tmp_path)
    finding_codes = {finding["code"] for finding in report["findings"]}

    assert code == 1
    assert "SYMLINK_NOT_ALLOWED" in finding_codes
    assert "CREDENTIAL_FILENAME" in finding_codes
