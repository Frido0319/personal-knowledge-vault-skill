from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .github import prepare_private_mirror, publish_private_mirror
from .integrations import run_qmd_update, run_restic_backup
from .proposals import list_proposals
from .review import promote_proposal, reject_proposal
from .search import search_vault
from .skill_catalog import build_skill_catalog
from .sources import add_source, disable_source, enable_source, list_sources
from .status import collect_status
from .update import run_update
from .config import load_config


class ActionError(ValueError):
    """Raised when a web action is outside the fixed operation contract."""


class WebActionService:
    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path).expanduser()

    def status(self) -> dict[str, Any]:
        return collect_status(self.config_path)

    def sources(self) -> list[dict[str, Any]]:
        return list_sources(self.config_path)

    def proposals(self) -> list[dict[str, Any]]:
        return list_proposals(self.config_path)

    def search(self, query: str) -> list[dict[str, Any]]:
        if len(query) > 500:
            raise ActionError("QUERY_TOO_LONG")
        config = load_config(self.config_path)
        return search_vault(config["vault"], query, limit=30)

    @staticmethod
    def _apply_mode(mode: str, confirm: bool) -> bool:
        if mode == "preview":
            return False
        if mode != "apply":
            raise ActionError("INVALID_MODE")
        if not confirm:
            raise ActionError("APPLY_CONFIRMATION_REQUIRED")
        return True

    def update(self, *, mode: str, confirm: bool) -> dict[str, Any]:
        return run_update(self.config_path, apply=self._apply_mode(mode, confirm))

    def skill_catalog(self, *, mode: str, confirm: bool) -> dict[str, Any]:
        return build_skill_catalog(self.config_path, apply=self._apply_mode(mode, confirm))

    def qmd(self, *, mode: str, confirm: bool) -> dict[str, Any]:
        return run_qmd_update(self.config_path, apply=self._apply_mode(mode, confirm))

    def backup(self, *, mode: str, confirm: bool) -> dict[str, Any]:
        return run_restic_backup(self.config_path, apply=self._apply_mode(mode, confirm))

    def github(self, *, mode: str, confirm: bool, confirmation: str = "") -> dict[str, Any]:
        if mode == "preview":
            return prepare_private_mirror(self.config_path, apply=False)
        if mode == "prepare":
            if not confirm:
                raise ActionError("APPLY_CONFIRMATION_REQUIRED")
            return prepare_private_mirror(self.config_path, apply=True)
        if mode == "publish":
            if not confirm:
                raise ActionError("APPLY_CONFIRMATION_REQUIRED")
            return publish_private_mirror(self.config_path, confirmation=confirmation)
        raise ActionError("INVALID_MODE")

    def source(self, *, action: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if action == "add":
            try:
                return add_source(
                    self.config_path,
                    source_id=str(payload["id"]),
                    kind=str(payload["kind"]),
                    path=str(payload["path"]),
                )
            except KeyError as exc:
                raise ActionError("SOURCE_FIELDS_REQUIRED") from exc
        if action == "enable":
            return enable_source(
                self.config_path,
                str(payload.get("id", "")),
                confirmation=str(payload.get("confirmation", "")),
            )
        if action == "disable":
            return disable_source(self.config_path, str(payload.get("id", "")))
        raise ActionError("SOURCE_ACTION_NOT_ALLOWED")

    def review(self, *, action: str, proposal_id: str, confirmation: str) -> dict[str, Any]:
        if action == "promote":
            return promote_proposal(self.config_path, proposal_id, confirmation=confirmation)
        if action == "reject":
            return reject_proposal(self.config_path, proposal_id, confirmation=confirmation)
        raise ActionError("REVIEW_ACTION_NOT_ALLOWED")

