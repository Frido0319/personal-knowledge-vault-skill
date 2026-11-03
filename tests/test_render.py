from pathlib import Path

from personal_vault.inventory import scan_source
from personal_vault.render import GENERATED_BY, render_vault


FIXTURES = Path(__file__).parent / "fixtures"


def test_chinese_render_has_readable_hierarchy_and_source_links() -> None:
    projects = scan_source(
        {"id": "projects", "kind": "project", "path": str(FIXTURES / "synthetic-project"), "enabled": True}
    )
    learning = scan_source(
        {"id": "learning", "kind": "learning", "path": str(FIXTURES / "synthetic-learning"), "enabled": True}
    )

    pages = render_vault(language="zh-CN", inventories=[projects, learning])

    assert "00-首页.md" in pages
    assert "map/知识地图.md" in pages
    assert "projects/projects/ProjectAlpha.md" in pages
    assert "projects/projects/ProjectAlpha/知识导航.md" in pages
    assert "references/projects/ProjectAlpha-来源证据.md" in pages
    home = pages["00-首页.md"]
    project = pages["projects/projects/ProjectAlpha.md"]
    assert "项目" in home and "学习" in home and "待审核知识" in home
    assert "map_level: 3" in project
    assert "map_level: 4" in pages["projects/projects/ProjectAlpha/知识导航.md"]
    assert "map_level: 5" in pages["references/projects/ProjectAlpha-来源证据.md"]
    assert "本机来源" in project
    assert "Project Alpha builds" in project
    assert f"generated_by: {GENERATED_BY}" in project


def test_english_render_uses_english_navigation() -> None:
    inventory = scan_source(
        {"id": "projects", "kind": "project", "path": str(FIXTURES / "synthetic-project"), "enabled": True}
    )

    pages = render_vault(language="en", inventories=[inventory])

    assert "map/Knowledge Map.md" in pages
    assert "Authorized sources" in pages["00-Home.md"]
    assert "Local source" in pages["projects/projects/ProjectAlpha.md"]


def test_render_contains_no_raw_conversation_nodes() -> None:
    pages = render_vault(language="zh-CN", inventories=[])

    assert all(not path.startswith("_raw/") for path in pages)
    assert all("会话原文" not in body for body in pages.values())
