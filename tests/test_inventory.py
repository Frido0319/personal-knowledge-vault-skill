from pathlib import Path

from personal_vault.inventory import scan_source


FIXTURES = Path(__file__).parent / "fixtures"


def test_project_inventory_covers_each_top_level_item_and_hashes_files() -> None:
    inventory = scan_source(
        {"id": "projects", "kind": "project", "path": str(FIXTURES / "synthetic-project"), "enabled": True}
    )

    assert [item.title for item in inventory.items] == ["ProjectAlpha", "ProjectBeta"]
    alpha = inventory.items[0]
    assert alpha.file_count == 2
    assert alpha.content_hash and len(alpha.content_hash) == 64
    assert "local-first research dashboard" in alpha.summary
    assert "alpha@example.com" not in alpha.summary
    assert "[REDACTED:email]" in alpha.summary


def test_inventory_excludes_sensitive_cache_and_out_of_root_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    project = root / "SafeProject"
    project.mkdir(parents=True)
    (project / "README.md").write_text("# Safe\nUseful summary.\n", encoding="utf-8")
    (project / ".env").write_text("TOKEN=should-never-appear", encoding="utf-8")
    (project / "node_modules").mkdir()
    (project / "node_modules" / "junk.js").write_text("junk", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("private outside", encoding="utf-8")
    (project / "outside-link").symlink_to(outside)

    inventory = scan_source({"id": "safe", "kind": "project", "path": str(root), "enabled": True})

    relative_paths = [record.relative_path for record in inventory.items[0].files]
    assert relative_paths == ["README.md"]
    assert inventory.excluded == 3
    assert "should-never-appear" not in inventory.items[0].summary


def test_direct_skill_repository_is_one_item(tmp_path: Path) -> None:
    root = tmp_path / "my-skill"
    root.mkdir()
    (root / "SKILL.md").write_text("---\nname: my-skill\ndescription: Does one thing.\n---\n# My Skill\n", encoding="utf-8")

    inventory = scan_source({"id": "my-skill", "kind": "skill", "path": str(root), "enabled": True})

    assert len(inventory.items) == 1
    assert inventory.items[0].title == "my-skill"
    assert inventory.items[0].files[0].relative_path == "SKILL.md"


def test_inventory_is_deterministic() -> None:
    source = {"id": "projects", "kind": "project", "path": str(FIXTURES / "synthetic-project"), "enabled": True}

    first = scan_source(source)
    second = scan_source(source)

    assert first == second

