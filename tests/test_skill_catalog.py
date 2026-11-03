from pathlib import Path

import pytest

from personal_vault.paths import VaultPaths
from personal_vault.setup import initialize
from personal_vault.skill_catalog import (
    SkillCatalogError,
    add_github_skill,
    build_skill_catalog,
    list_github_skills,
)


COMMIT = "a" * 40


def _configured(tmp_path: Path) -> VaultPaths:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="zh-CN")
    return paths


@pytest.mark.parametrize("ownership", ["authored", "maintained", "vendored"])
def test_add_skill_preserves_ownership_and_fixed_commit(tmp_path: Path, ownership: str) -> None:
    paths = _configured(tmp_path)

    entry = add_github_skill(
        Path(paths.config),
        repository=f"example/{ownership}-skill",
        ownership=ownership,
        commit=COMMIT,
        skill_path="skills/example/SKILL.md",
        summary="A bounded example skill.",
    )

    assert entry["ownership"] == ownership
    assert entry["permalink"] == f"https://github.com/example/{ownership}-skill/blob/{COMMIT}/skills/example/SKILL.md"
    assert list_github_skills(Path(paths.config))[0]["repository"].startswith("example/")


def test_skill_catalog_renders_readable_index_and_immutable_permalink(tmp_path: Path) -> None:
    paths = _configured(tmp_path)
    add_github_skill(
        Path(paths.config),
        repository="example/my-skill",
        ownership="authored",
        commit=COMMIT,
        summary="Builds a private knowledge workflow.",
    )

    result = build_skill_catalog(Path(paths.config), apply=True)

    page = Path(paths.vault) / "skills" / "我的Skills" / "example--my-skill.md"
    assert result["created"] == 2
    content = page.read_text(encoding="utf-8")
    assert "ownership: authored" in content
    assert f"blob/{COMMIT}/SKILL.md" in content
    assert "Builds a private knowledge workflow" in content
    assert build_skill_catalog(Path(paths.config), apply=False)["changes"] == []


def test_skill_catalog_never_overwrites_manual_page(tmp_path: Path) -> None:
    paths = _configured(tmp_path)
    add_github_skill(Path(paths.config), repository="example/my-skill", ownership="authored", commit=COMMIT)
    target = Path(paths.vault) / "skills" / "我的Skills" / "example--my-skill.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Manual skill note\n", encoding="utf-8")

    result = build_skill_catalog(Path(paths.config), apply=True)

    assert result["protected"] == 1
    assert target.read_text(encoding="utf-8") == "# Manual skill note\n"


@pytest.mark.parametrize(
    "repository,ownership,commit,code",
    [
        ("../escape", "authored", COMMIT, "REPOSITORY"),
        ("example/skill", "owner", COMMIT, "OWNERSHIP"),
        ("example/skill", "authored", "main", "COMMIT"),
    ],
)
def test_skill_metadata_is_strict(
    tmp_path: Path, repository: str, ownership: str, commit: str, code: str
) -> None:
    paths = _configured(tmp_path)

    with pytest.raises(SkillCatalogError, match=code):
        add_github_skill(
            Path(paths.config),
            repository=repository,
            ownership=ownership,
            commit=commit,
        )


def test_duplicate_skill_repository_is_rejected(tmp_path: Path) -> None:
    paths = _configured(tmp_path)
    add_github_skill(Path(paths.config), repository="example/skill", ownership="authored", commit=COMMIT)

    with pytest.raises(SkillCatalogError, match="DUPLICATE"):
        add_github_skill(Path(paths.config), repository="example/skill", ownership="authored", commit=COMMIT)

