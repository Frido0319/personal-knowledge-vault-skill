from __future__ import annotations

from pathlib import Path, PurePosixPath
import re
from typing import Any

from .config import load_config, write_config_atomic
from .proposals import _atomic_text
from .security import redact_text


GENERATOR = "personal-knowledge-vault-skill-catalog"
OWNERSHIP = {"authored", "maintained", "vendored"}
_REPOSITORY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
_COMMIT = re.compile(r"^[0-9a-fA-F]{40}$")


class SkillCatalogError(ValueError):
    """Raised for unsafe or ambiguous Skill provenance metadata."""


def _validate_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.name:
        raise SkillCatalogError("SKILL_PATH_INVALID")
    return path.as_posix()


def list_github_skills(config_path: str | Path) -> list[dict[str, Any]]:
    config = load_config(config_path)
    skills = config.get("skills", [])
    if not isinstance(skills, list):
        raise SkillCatalogError("SKILLS_LIST_REQUIRED")
    return [dict(skill) for skill in skills if isinstance(skill, dict)]


def add_github_skill(
    config_path: str | Path,
    *,
    repository: str,
    ownership: str,
    commit: str,
    skill_path: str = "SKILL.md",
    summary: str = "",
) -> dict[str, Any]:
    if not _REPOSITORY.fullmatch(repository) or ".." in repository:
        raise SkillCatalogError("REPOSITORY_INVALID")
    if ownership not in OWNERSHIP:
        raise SkillCatalogError("OWNERSHIP_INVALID")
    if not _COMMIT.fullmatch(commit):
        raise SkillCatalogError("COMMIT_INVALID")
    normalized_path = _validate_path(skill_path)
    config_file = Path(config_path).expanduser()
    config = load_config(config_file)
    skills = config.setdefault("skills", [])
    if not isinstance(skills, list):
        raise SkillCatalogError("SKILLS_LIST_REQUIRED")
    if any(isinstance(skill, dict) and str(skill.get("repository", "")).casefold() == repository.casefold() for skill in skills):
        raise SkillCatalogError("DUPLICATE_SKILL_REPOSITORY")
    commit = commit.casefold()
    entry = {
        "repository": repository,
        "ownership": ownership,
        "commit": commit,
        "skill_path": normalized_path,
        "summary": redact_text(summary.strip()),
        "permalink": f"https://github.com/{repository}/blob/{commit}/{normalized_path}",
    }
    skills.append(entry)
    skills.sort(key=lambda item: str(item.get("repository", "")).casefold())
    write_config_atomic(config_file, config)
    return dict(entry)


def _owned(text: str) -> bool:
    return bool(re.search(rf"^generated_by:\s*{re.escape(GENERATOR)}\s*$", text[:1000], re.MULTILINE))


def _render_skill(entry: dict[str, Any], *, language: str) -> str:
    title = str(entry["repository"]).split("/", 1)[1]
    summary = entry.get("summary") or ("尚未填写摘要。" if language == "zh-CN" else "No summary has been supplied.")
    labels = (
        ("解决的问题", "归属", "固定版本", "GitHub 仓库", "不可变 SKILL.md")
        if language == "zh-CN"
        else ("What it solves", "Ownership", "Pinned version", "GitHub repository", "Immutable SKILL.md")
    )
    return (
        "---\n"
        f'title: "{title}"\n'
        f"generated_by: {GENERATOR}\n"
        "map_level: 3\n"
        f"ownership: {entry['ownership']}\n"
        f"repository: {entry['repository']}\n"
        f"commit: {entry['commit']}\n"
        "---\n\n"
        f"# {title}\n\n"
        f"## {labels[0]}\n\n{summary}\n\n"
        f"- {labels[1]}：`{entry['ownership']}`\n"
        f"- {labels[2]}：`{entry['commit']}`\n"
        f"- {labels[3]}：[https://github.com/{entry['repository']}](https://github.com/{entry['repository']})\n"
        f"- {labels[4]}：[{entry['skill_path']}]({entry['permalink']})\n"
    )


def _render_index(entries: list[dict[str, Any]], *, language: str, folder: str) -> str:
    title = "我的 Skills" if language == "zh-CN" else "My Skills"
    header = "| Skill | 归属 | 固定 commit |" if language == "zh-CN" else "| Skill | Ownership | Pinned commit |"
    rows = []
    for entry in entries:
        slug = str(entry["repository"]).replace("/", "--")
        title_value = str(entry["repository"]).split("/", 1)[1]
        rows.append(f"| [[skills/{folder}/{slug}|{title_value}]] | {entry['ownership']} | `{str(entry['commit'])[:12]}` |")
    return (
        "---\n"
        f'title: "{title}"\n'
        f"generated_by: {GENERATOR}\n"
        "map_level: 2\n"
        "---\n\n"
        f"# {title}\n\n{header}\n|---|---|---|\n"
        + ("\n".join(rows) if rows else "| - | - | - |")
        + "\n"
    )


def build_skill_catalog(config_path: str | Path, *, apply: bool = False) -> dict[str, Any]:
    config = load_config(config_path)
    entries = list_github_skills(config_path)
    language = str(config["language"])
    folder = "我的Skills" if language == "zh-CN" else "My Skills"
    pages: dict[str, str] = {
        f"skills/{folder}/00-{'索引' if language == 'zh-CN' else 'Index'}.md": _render_index(entries, language=language, folder=folder)
    }
    for entry in entries:
        slug = str(entry["repository"]).replace("/", "--")
        pages[f"skills/{folder}/{slug}.md"] = _render_skill(entry, language=language)
    vault = Path(str(config["vault"])).expanduser()
    changes: list[dict[str, str]] = []
    counts = {"created": 0, "updated": 0, "unchanged": 0, "protected": 0, "removed": 0}
    for relative, content in sorted(pages.items()):
        target = vault / relative
        if not target.exists():
            counts["created"] += 1
            changes.append({"action": "create", "path": relative})
            continue
        try:
            current = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            counts["protected"] += 1
            changes.append({"action": "protect", "path": relative})
            continue
        if current == content:
            counts["unchanged"] += 1
        elif _owned(current):
            counts["updated"] += 1
            changes.append({"action": "update", "path": relative})
        else:
            counts["protected"] += 1
            changes.append({"action": "protect", "path": relative})
    root = vault / "skills" / folder
    if root.is_dir():
        for target in root.glob("*.md"):
            relative = target.relative_to(vault).as_posix()
            if relative in pages:
                continue
            try:
                current = target.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            if _owned(current):
                counts["removed"] += 1
                changes.append({"action": "remove", "path": relative})
    if apply:
        for change in changes:
            target = vault / change["path"]
            if change["action"] in {"create", "update"}:
                _atomic_text(target, pages[change["path"]])
            elif change["action"] == "remove" and target.is_file():
                target.unlink()
    return {**counts, "skills": len(entries), "applied": apply, "changes": sorted(changes, key=lambda item: item["path"])}

