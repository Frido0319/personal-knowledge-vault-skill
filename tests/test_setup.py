from pathlib import Path

from personal_vault.config import load_config
from personal_vault.paths import VaultPaths
from personal_vault.setup import initialize


def test_initialize_creates_private_empty_layout(tmp_path: Path) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")

    result = initialize(paths=paths, language="zh-CN")

    assert result["created"] > 0
    assert Path(paths.config).is_file()
    assert load_config(Path(paths.config))["sources"] == []
    assert (Path(paths.vault) / ".obsidian").is_dir()
    assert not (Path(paths.vault) / "_raw").exists()
    assert not (Path(paths.vault) / "_staging").exists()


def test_initialize_is_idempotent(tmp_path: Path) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="en")
    before = Path(paths.config).read_bytes()

    result = initialize(paths=paths, language="en")

    assert result["created"] == 0
    assert Path(paths.config).read_bytes() == before


def test_initialize_dry_run_is_strictly_zero_write(tmp_path: Path) -> None:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")

    result = initialize(paths=paths, language="zh-CN", dry_run=True)

    assert result["would_create"]
    assert not Path(paths.vault).exists()
    assert not Path(paths.data).exists()


def test_initialize_refuses_private_data_inside_repo(tmp_path: Path) -> None:
    repo = tmp_path / "source-repo"
    repo.mkdir()
    paths = VaultPaths.from_roots(repo / "vault", tmp_path / "data")

    try:
        initialize(paths=paths, language="zh-CN", repo_root=repo)
    except ValueError as exc:
        assert "SOURCE_REPOSITORY" in str(exc)
    else:
        raise AssertionError("unsafe layout was accepted")

