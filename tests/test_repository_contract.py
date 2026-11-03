from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_documentation_explains_product_and_boundaries() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs" / "operations.md").read_text(encoding="utf-8")
    threat_model = (ROOT / "docs" / "threat-model.md").read_text(encoding="utf-8")

    assert "active construction" not in readme.casefold()
    for phrase in ("中文", "Linux", "Windows", "Obsidian", "PRIVATE", "_staging", "快速开始"):
        assert phrase in readme
    for phrase in ("update", "upgrade", "Restic", "恢复", "schedule"):
        assert phrase.casefold() in operations.casefold()
    for phrase in ("资产", "信任边界", "威胁", "剩余风险", "浏览器", "符号链接"):
        assert phrase in threat_model


def test_ci_runs_on_ubuntu_and_native_windows() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "ubuntu-latest" in workflow
    assert "windows-latest" in workflow
    assert "pytest" in workflow
    assert "privacy_audit.py" in workflow
    assert "synthetic_acceptance.py" in workflow
    assert "ScriptBlock" in workflow
    assert "wsl" not in workflow.casefold()


def test_release_workflow_builds_and_publishes_checksums() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "tags:" in workflow and "v*" in workflow
    assert "build_release.py" in workflow
    assert "SHA256SUMS" in workflow
    assert "gh release create" in workflow
    assert "contents: write" in workflow
