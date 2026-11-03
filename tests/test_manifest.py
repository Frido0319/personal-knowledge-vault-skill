from pathlib import Path

from personal_vault.manifest import ManifestStore, load_page_records


def test_manifest_upsert_is_idempotent_and_separates_sources(tmp_path: Path) -> None:
    path = tmp_path / "state" / "manifest.sqlite"
    with ManifestStore(path) as store:
        store.upsert_page("projects/a.md", source_id="projects", content_hash="a" * 64)
        store.upsert_page("projects/a.md", source_id="projects", content_hash="a" * 64)
        store.upsert_page("learning/a.md", source_id="learning", content_hash="b" * 64)

    records = load_page_records(path)
    assert set(records) == {"projects/a.md", "learning/a.md"}
    assert records["projects/a.md"]["content_hash"] == "a" * 64


def test_reading_absent_manifest_is_zero_write(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "manifest.sqlite"

    assert load_page_records(path) == {}
    assert not path.parent.exists()

