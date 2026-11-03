from pathlib import Path

from personal_vault.cli import main


def test_cli_init_and_source_workflow(tmp_path: Path, capsys) -> None:
    vault = tmp_path / "vault"
    data = tmp_path / "data"
    source = tmp_path / "projects"
    source.mkdir()

    assert main(["init", "--vault", str(vault), "--data", str(data), "--language", "zh-CN"]) == 0
    assert main(
        [
            "source",
            "add",
            "--config",
            str(data / "config" / "config.yaml"),
            "--id",
            "projects",
            "--kind",
            "project",
            "--path",
            str(source),
        ]
    ) == 0
    assert main(
        [
            "source",
            "enable",
            "--config",
            str(data / "config" / "config.yaml"),
            "--id",
            "projects",
            "--confirmation",
            "ENABLE:projects",
        ]
    ) == 0

    output = capsys.readouterr().out
    assert '"enabled": true' in output
    assert str(source) in output


def test_cli_init_dry_run_leaves_no_path(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    data = tmp_path / "data"

    assert main(["init", "--vault", str(vault), "--data", str(data), "--dry-run"]) == 0

    assert not vault.exists()
    assert not data.exists()


def test_cli_update_requires_explicit_preview_or_apply(tmp_path: Path, capsys) -> None:
    vault = tmp_path / "vault"
    data = tmp_path / "data"
    assert main(["init", "--vault", str(vault), "--data", str(data)]) == 0
    config = data / "config" / "config.yaml"

    assert main(["update", "--config", str(config), "--preview"]) == 0
    assert not (vault / "00-首页.md").exists()
    assert main(["update", "--config", str(config), "--apply"]) == 0
    assert (vault / "00-首页.md").is_file()

    output = capsys.readouterr().out
    assert '"applied": false' in output
    assert '"applied": true' in output
