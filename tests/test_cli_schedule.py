from pathlib import Path

from personal_vault.cli import main
from personal_vault.paths import VaultPaths
from personal_vault.setup import initialize


def test_cli_schedule_show_is_read_only(tmp_path: Path, capsys) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="zh-CN")
    before = Path(paths.config).read_bytes()

    assert main(["schedule", "show", "--config", str(paths.config)]) == 0

    output = capsys.readouterr().out
    assert "personal-vault-maintenance.timer" in output
    assert Path(paths.config).read_bytes() == before

