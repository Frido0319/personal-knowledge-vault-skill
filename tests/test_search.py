from pathlib import Path

from personal_vault.search import search_vault


def test_search_finds_chinese_and_english_terms_but_excludes_raw_and_staging(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "knowledge").mkdir(parents=True)
    (vault / "_staging").mkdir()
    (vault / "_raw").mkdir()
    (vault / "knowledge" / "retrieval.md").write_text(
        "# 检索设计\n\nQMD 提供 local-first semantic retrieval。\n",
        encoding="utf-8",
    )
    (vault / "_staging" / "secret.md").write_text("# 检索草稿\nprivate staging", encoding="utf-8")
    (vault / "_raw" / "chat.md").write_text("# 检索会话\nraw chat", encoding="utf-8")

    chinese = search_vault(vault, "检索")
    english = search_vault(vault, "semantic retrieval")

    assert [result["path"] for result in chinese] == ["knowledge/retrieval.md"]
    assert english[0]["title"] == "检索设计"
    assert "local-first" in english[0]["snippet"]


def test_search_is_ranked_bounded_and_does_not_return_full_document(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    for index in range(4):
        (vault / f"note-{index}.md").write_text(
            f"# Note {index}\n\nkeyword " + ("keyword " * index) + ("x" * 2000),
            encoding="utf-8",
        )

    results = search_vault(vault, "keyword", limit=2)

    assert len(results) == 2
    assert results[0]["score"] >= results[1]["score"]
    assert len(results[0]["snippet"]) <= 320


def test_blank_query_returns_no_result(tmp_path: Path) -> None:
    assert search_vault(tmp_path, "   ") == []


def test_search_snippet_hides_frontmatter_and_markdown_noise(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "page.md").write_text(
        "---\ntitle: Noisy\ngenerated_by: test\nmap_level: 3\n---\n\n# Clean title\n\n[[map/Root|Readable link]] contains the target phrase.\n",
        encoding="utf-8",
    )

    result = search_vault(vault, "target phrase")[0]

    assert "generated_by" not in result["snippet"]
    assert "---" not in result["snippet"]
    assert "Readable link" in result["snippet"]
    assert "[[" not in result["snippet"]
