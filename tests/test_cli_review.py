from pathlib import Path

from personal_vault.cli import main
from personal_vault.paths import VaultPaths
from personal_vault.setup import initialize
from personal_vault.sources import add_source, enable_source


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic-proposals.json"


def test_cli_stage_list_promote_workflow(tmp_path: Path, capsys) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="zh-CN")
    export = tmp_path / "history"
    export.mkdir()
    add_source(Path(paths.config), source_id="agent-history", kind="agent_history", path=export)
    enable_source(Path(paths.config), "agent-history", confirmation="AUTHORIZE:agent-history:agent_history")

    assert main(["stage", "add", "--config", str(paths.config), "--input", str(FIXTURE)]) == 0
    assert main(["stage", "list", "--config", str(paths.config)]) == 0
    assert main(
        [
            "review",
            "promote",
            "--config",
            str(paths.config),
            "--id",
            "local-first-rule",
            "--confirmation",
            "PROMOTE:local-first-rule",
        ]
    ) == 0

    assert (Path(paths.vault) / "knowledge" / "local-first-rule.md").is_file()
    output = capsys.readouterr().out
    assert '"status": "approved"' in output
