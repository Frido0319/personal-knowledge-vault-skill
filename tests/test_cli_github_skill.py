from pathlib import Path

from personal_vault.cli import main
from personal_vault.paths import VaultPaths
from personal_vault.setup import initialize


def test_cli_add_list_and_catalog_skill(tmp_path: Path, capsys) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="zh-CN")
    commit = "c" * 40

    assert main(
        [
            "skill",
            "add",
            "--config",
            str(paths.config),
            "--repository",
            "example/useful-skill",
            "--ownership",
            "authored",
            "--commit",
            commit,
            "--summary",
            "A useful workflow.",
        ]
    ) == 0
    assert main(["skill", "list", "--config", str(paths.config)]) == 0
    assert main(["skill", "catalog", "--config", str(paths.config), "--apply"]) == 0

    assert (Path(paths.vault) / "skills" / "我的Skills" / "example--useful-skill.md").is_file()
    output = capsys.readouterr().out
    assert "example/useful-skill" in output
    assert '"ownership": "authored"' in output


def test_cli_github_prepare_parser_is_explicit_about_preview_or_apply(tmp_path: Path) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="en")

    # The command reaches the disabled integration instead of accepting an
    # implicit write mode. Errors are returned as structured nonzero results.
    assert main(["github", "prepare", "--config", str(paths.config), "--preview"]) == 1

