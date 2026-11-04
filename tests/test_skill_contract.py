from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "build-personal-knowledge-vault"


def _load_installer():
    path = SKILL / "scripts" / "install_runtime.py"
    spec = importlib.util.spec_from_file_location("skill_install_runtime", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frontmatter(text: str) -> dict[str, object]:
    assert text.startswith("---\n")
    _, raw, _ = text.split("---", 2)
    payload = yaml.safe_load(raw)
    assert isinstance(payload, dict)
    return payload


def test_skill_metadata_is_minimal_and_triggerable() -> None:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    metadata = _frontmatter(text)

    assert set(metadata) == {"name", "description"}
    assert metadata["name"] == "build-personal-knowledge-vault"
    description = str(metadata["description"]).casefold()
    for phrase in ("obsidian", "linux", "windows", "knowledge", "private"):
        assert phrase in description


def test_skill_encodes_privacy_review_and_cross_platform_contracts() -> None:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    folded = text.casefold()

    for forbidden in ("todo", "[placeholder", "structuring this skill"):
        assert forbidden not in folded
    for required in (
        "显式授权",
        "禁止自动扫描",
        "_staging",
        "人工",
        "原生 windows",
        "不要求 wsl",
        "不默认安装本地大模型",
        "update",
        "upgrade",
        "private",
    ):
        assert required.casefold() in folded


def test_skill_references_and_scripts_are_present() -> None:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    required = (
        "references/privacy-boundary.md",
        "references/platform-installation.md",
        "references/update-and-recovery.md",
        "references/acceptance-checklist.md",
        "scripts/install_runtime.py",
        "scripts/verify_install.py",
    )
    for relative in required:
        assert relative in text
        assert (SKILL / relative).is_file()


def test_installer_only_accepts_a_hash_verified_bundled_runtime() -> None:
    installer = (SKILL / "scripts" / "install_runtime.py").read_text(encoding="utf-8")
    folded = installer.casefold()

    assert "sha256sums" in folded
    assert "hashlib.sha256" in folded
    assert "assets" in folded and "runtime" in folded
    assert "--allow-network" in installer
    assert "urllib" not in folded
    assert "requests" not in folded


def test_openai_metadata_invokes_literal_skill_name() -> None:
    payload = yaml.safe_load((SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8"))
    interface = payload["interface"]

    assert 25 <= len(interface["short_description"]) <= 64
    assert "$build-personal-knowledge-vault" in interface["default_prompt"]
    assert "\\$build-personal-knowledge-vault" not in interface["default_prompt"]


def test_config_templates_match_runtime_top_level_shape() -> None:
    for language in ("zh-CN", "en"):
        payload = yaml.safe_load(
            (SKILL / "assets" / "config-templates" / f"config.{language}.yaml").read_text(encoding="utf-8")
        )
        assert payload["language"] == language
        assert payload["sources"] == []
        assert payload["skills"] == []
        assert payload["schedule"]["enabled"] is False


def test_installer_previews_verified_wheel_and_rejects_tampering(tmp_path: Path) -> None:
    installer = _load_installer()
    runtime = tmp_path / "assets" / "runtime"
    runtime.mkdir(parents=True)
    wheel = runtime / "personal_knowledge_vault-0.1.1-py3-none-any.whl"
    wheel.write_bytes(b"synthetic-wheel")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    (runtime / "SHA256SUMS").write_text(f"{digest}  {wheel.name}\n", encoding="utf-8")
    target = tmp_path / "venv"

    preview = installer.install_runtime(
        skill_root=tmp_path,
        target=target,
        apply=False,
        allow_network=False,
    )

    assert preview["sha256"] == digest
    assert preview["applied"] is False
    assert not target.exists()

    wheel.write_bytes(b"tampered")
    with pytest.raises(installer.InstallerError, match="WHEEL_HASH_MISMATCH"):
        installer.verify_bundled_wheel(tmp_path)
