from pathlib import Path, PureWindowsPath

import pytest

from personal_vault.paths import PathBoundaryError, VaultPaths, default_paths


def test_linux_defaults_live_outside_source_tree(tmp_path: Path) -> None:
    home = tmp_path / "home"
    paths = default_paths(os_name="posix", home=home)

    assert paths.vault == home / "Documents" / "PersonalKnowledgeVault"
    assert paths.data == home / ".local" / "share" / "personal-vault"
    assert paths.config == paths.data / "config" / "config.yaml"
    assert paths.manifest == paths.data / "state" / "manifest.sqlite"


def test_windows_defaults_are_native_and_do_not_require_wsl() -> None:
    home = PureWindowsPath("C:/") / "Users" / "Alice"
    paths = default_paths(
        os_name="nt",
        home=home,
        local_appdata=home / "AppData" / "Local",
    )

    assert paths.vault == home / "Documents" / "PersonalKnowledgeVault"
    assert paths.data == home / "AppData" / "Local" / "PersonalVault"
    assert "wsl" not in str(paths.data).lower()


def test_paths_reject_vault_or_data_inside_source_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    paths = VaultPaths.from_roots(repo / "vault", tmp_path / "data")

    with pytest.raises(PathBoundaryError, match="SOURCE_REPOSITORY"):
        paths.validate(repo_root=repo)


def test_paths_reject_overlapping_vault_and_data(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    paths = VaultPaths.from_roots(vault, vault / ".data")

    with pytest.raises(PathBoundaryError, match="OVERLAP"):
        paths.validate()
