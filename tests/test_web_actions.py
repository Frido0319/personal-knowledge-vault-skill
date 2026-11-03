from pathlib import Path

import pytest

from personal_vault.paths import VaultPaths
from personal_vault.setup import initialize
from personal_vault.web_actions import ActionError, WebActionService


def _service(tmp_path: Path) -> tuple[VaultPaths, WebActionService]:
    paths = VaultPaths.from_roots(tmp_path / "vault", tmp_path / "data")
    initialize(paths=paths, language="zh-CN")
    return paths, WebActionService(Path(paths.config))


def test_update_requires_preview_or_confirmed_apply(tmp_path: Path) -> None:
    paths, service = _service(tmp_path)

    preview = service.update(mode="preview", confirm=False)
    assert preview["applied"] is False
    assert not (Path(paths.vault) / "00-首页.md").exists()

    with pytest.raises(ActionError, match="CONFIRMATION"):
        service.update(mode="apply", confirm=False)

    applied = service.update(mode="apply", confirm=True)
    assert applied["applied"] is True
    assert (Path(paths.vault) / "00-首页.md").is_file()


def test_service_exposes_bounded_status_sources_review_and_search(tmp_path: Path) -> None:
    paths, service = _service(tmp_path)
    knowledge = Path(paths.vault) / "knowledge"
    knowledge.mkdir()
    (knowledge / "note.md").write_text("# 检索知识\n\nReviewed content.\n", encoding="utf-8")

    assert service.status()["vault"]["formal_pages"] == 1
    assert service.sources() == []
    assert service.proposals() == []
    assert service.search("检索")[0]["path"] == "knowledge/note.md"


def test_service_rejects_unknown_modes_and_actions(tmp_path: Path) -> None:
    _, service = _service(tmp_path)

    with pytest.raises(ActionError, match="MODE"):
        service.update(mode="now", confirm=True)
    with pytest.raises(ActionError, match="SOURCE_ACTION"):
        service.source(action="shell", payload={"command": "rm -rf /"})
    with pytest.raises(ActionError, match="REVIEW_ACTION"):
        service.review(action="edit", proposal_id="x", confirmation="x")


def test_search_query_is_bounded(tmp_path: Path) -> None:
    _, service = _service(tmp_path)

    with pytest.raises(ActionError, match="QUERY_TOO_LONG"):
        service.search("x" * 501)

