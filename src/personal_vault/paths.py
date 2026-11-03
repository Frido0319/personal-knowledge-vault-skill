from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PurePath, PureWindowsPath
from typing import TypeVar


class PathBoundaryError(ValueError):
    """Raised when private data would overlap an unsafe path."""


P = TypeVar("P", bound=PurePath)


def _contains(parent: PurePath, child: PurePath) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _normalized(path: P) -> P:
    if isinstance(path, Path):
        return path.expanduser().resolve(strict=False)  # type: ignore[return-value]
    return path  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class VaultPaths:
    vault: PurePath
    data: PurePath

    @classmethod
    def from_roots(cls, vault: P, data: P) -> "VaultPaths":
        return cls(vault=_normalized(vault), data=_normalized(data))

    @property
    def config(self) -> PurePath:
        return self.data / "config" / "config.yaml"

    @property
    def manifest(self) -> PurePath:
        return self.data / "state" / "manifest.sqlite"

    @property
    def audit(self) -> PurePath:
        return self.data / "audit"

    @property
    def state(self) -> PurePath:
        return self.data / "state"

    def validate(self, *, repo_root: PurePath | None = None) -> None:
        vault = _normalized(self.vault)
        data = _normalized(self.data)
        if vault == data or _contains(vault, data) or _contains(data, vault):
            raise PathBoundaryError("VAULT_DATA_OVERLAP")
        if repo_root is None:
            return
        repo = _normalized(repo_root)
        if _contains(repo, vault) or _contains(repo, data):
            raise PathBoundaryError("PRIVATE_DATA_INSIDE_SOURCE_REPOSITORY")


def default_paths(
    *,
    os_name: str | None = None,
    home: PurePath | None = None,
    local_appdata: PurePath | None = None,
) -> VaultPaths:
    """Return native defaults without probing or creating the filesystem."""

    platform_name = os_name or os.name
    if platform_name == "nt":
        user_home = PureWindowsPath(home or Path.home())
        app_data = PureWindowsPath(
            local_appdata
            or os.environ.get("LOCALAPPDATA")
            or user_home / "AppData" / "Local"
        )
        return VaultPaths.from_roots(
            user_home / "Documents" / "PersonalKnowledgeVault",
            app_data / "PersonalVault",
        )
    user_home = Path(home or Path.home()).expanduser().resolve(strict=False)
    return VaultPaths.from_roots(
        user_home / "Documents" / "PersonalKnowledgeVault",
        user_home / ".local" / "share" / "personal-vault",
    )

