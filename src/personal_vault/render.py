from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from .inventory import ItemRecord, SourceInventory


GENERATED_BY = "personal-knowledge-vault"

_NAMESPACES = {
    "project": "projects",
    "learning": "learning",
    "documents": "documents",
    "skill": "skills",
    "agent_history": "knowledge",
    "weflow": "knowledge",
    "qq": "knowledge",
}


def _frontmatter(title: str, level: int, *, source_id: str = "system") -> str:
    safe_title = title.replace('"', "'")
    return (
        "---\n"
        f'title: "{safe_title}"\n'
        f"generated_by: {GENERATED_BY}\n"
        f"map_level: {level}\n"
        f"source_id: {source_id}\n"
        "---\n\n"
    )


def _source_uri(root: str, relative: str = ".") -> str:
    path = (Path(root) / relative).resolve(strict=False)
    try:
        return path.as_uri()
    except ValueError:
        return "file:///" + quote(str(path).replace("\\", "/"))


def _namespace(kind: str) -> str:
    return _NAMESPACES.get(kind, "references")


def _overview_page(language: str, inventory: SourceInventory, item: ItemRecord, detail_path: str, evidence_path: str) -> str:
    if language == "zh-CN":
        summary = item.summary or "尚无可提取的文本摘要；已保留文件清单和哈希证据。"
        body = [
            _frontmatter(item.title, 3, source_id=inventory.source_id),
            f"# {item.title}\n",
            "## 一眼看懂\n",
            summary + "\n",
            "## 当前状态\n",
            f"- 来源类型：`{inventory.kind}`",
            f"- 文件：{item.file_count} 个，共 {item.total_bytes} bytes",
            f"- 本机来源：[{item.relative_path}]({_source_uri(inventory.root, item.relative_path)})",
            f"- 局部导航：[[{detail_path}|项目内知识]]",
            f"- 来源证据：[[{evidence_path}|文件哈希与追溯]]\n",
            "## 人工维护区\n",
            "在独立手工页面记录已确认成果、下一步和决策；本生成页会随来源更新。\n",
        ]
    else:
        summary = item.summary or "No readable summary was extracted; file inventory and hash evidence remain available."
        body = [
            _frontmatter(item.title, 3, source_id=inventory.source_id),
            f"# {item.title}\n",
            "## At a glance\n",
            summary + "\n",
            "## Current state\n",
            f"- Source kind: `{inventory.kind}`",
            f"- Files: {item.file_count}, {item.total_bytes} bytes",
            f"- Local source: [{item.relative_path}]({_source_uri(inventory.root, item.relative_path)})",
            f"- Local navigation: [[{detail_path}|Project knowledge]]",
            f"- Source evidence: [[{evidence_path}|File hashes and provenance]]\n",
            "## Manual notes\n",
            "Keep confirmed outcomes, next actions, and decisions in a separate manual page; this generated page follows the source.\n",
        ]
    return "\n".join(body).rstrip() + "\n"


def _detail_page(language: str, inventory: SourceInventory, item: ItemRecord, overview_path: str, evidence_path: str) -> str:
    title = f"{item.title} - {'知识导航' if language == 'zh-CN' else 'Knowledge navigation'}"
    heading = "项目内知识导航" if language == "zh-CN" else "Local knowledge navigation"
    labels = ("返回概览", "来源证据", "该页用于承载后续人工或 AI 审核通过的 L4 主题链接。") if language == "zh-CN" else (
        "Back to overview",
        "Source evidence",
        "This page holds future L4 topic links approved by a human.",
    )
    return (
        _frontmatter(title, 4, source_id=inventory.source_id)
        + f"# {heading}\n\n"
        + f"- [[{overview_path}|{labels[0]}]]\n"
        + f"- [[{evidence_path}|{labels[1]}]]\n\n"
        + labels[2]
        + "\n"
    )


def _evidence_page(language: str, inventory: SourceInventory, item: ItemRecord, overview_path: str) -> str:
    title = f"{item.title} - {'来源证据' if language == 'zh-CN' else 'Source evidence'}"
    columns = "| 相对路径 | SHA-256 | 字节 |\n|---|---|---:|" if language == "zh-CN" else "| Relative path | SHA-256 | Bytes |\n|---|---|---:|"
    rows = [f"| `{record.relative_path}` | `{record.sha256}` | {record.size} |" for record in item.files]
    back = "返回项目概览" if language == "zh-CN" else "Back to overview"
    root_label = "授权根目录" if language == "zh-CN" else "Authorized root"
    return (
        _frontmatter(title, 5, source_id=inventory.source_id)
        + f"# {title}\n\n"
        + f"- [[{overview_path}|{back}]]\n"
        + f"- {root_label}：[{inventory.root}]({_source_uri(inventory.root)})\n"
        + f"- Content SHA-256：`{item.content_hash}`\n\n"
        + columns
        + "\n"
        + ("\n".join(rows) if rows else "| - | - | 0 |")
        + "\n"
    )


def render_vault(*, language: str, inventories: list[SourceInventory]) -> dict[str, str]:
    chinese = language == "zh-CN"
    home_path = "00-首页.md" if chinese else "00-Home.md"
    map_path = "map/知识地图.md" if chinese else "map/Knowledge Map.md"
    pages: dict[str, str] = {}

    source_links: list[str] = []
    item_links: list[str] = []
    for inventory in sorted(inventories, key=lambda item: item.source_id.casefold()):
        namespace = _namespace(inventory.kind)
        index_name = "00-索引.md" if chinese else "00-Index.md"
        index_path = f"{namespace}/{inventory.source_id}/{index_name}"
        source_links.append(f"- [[{index_path}|{inventory.source_id}]] ({len(inventory.items)})")
        index_rows: list[str] = []
        for item in inventory.items:
            overview_path = f"{namespace}/{inventory.source_id}/{item.item_id}.md"
            detail_path = f"{namespace}/{inventory.source_id}/{item.item_id}/{'知识导航' if chinese else 'Knowledge Navigation'}.md"
            evidence_path = f"references/{inventory.source_id}/{item.item_id}-{'来源证据' if chinese else 'Source Evidence'}.md"
            item_links.append(f"- [[{overview_path}|{item.title}]]")
            index_rows.append(f"| [[{overview_path}|{item.title}]] | {item.file_count} | {item.summary or '-'} |")
            pages[overview_path] = _overview_page(language, inventory, item, detail_path.removesuffix(".md"), evidence_path.removesuffix(".md"))
            pages[detail_path] = _detail_page(language, inventory, item, overview_path.removesuffix(".md"), evidence_path.removesuffix(".md"))
            pages[evidence_path] = _evidence_page(language, inventory, item, overview_path.removesuffix(".md"))
        title = f"{inventory.source_id} - {'来源索引' if chinese else 'Source index'}"
        header = "| 条目 | 文件数 | 摘要 |\n|---|---:|---|" if chinese else "| Item | Files | Summary |\n|---|---:|---|"
        pages[index_path] = (
            _frontmatter(title, 2, source_id=inventory.source_id)
            + f"# {title}\n\n"
            + f"{'授权根目录' if chinese else 'Authorized root'}：[{inventory.root}]({_source_uri(inventory.root)})\n\n"
            + header
            + "\n"
            + ("\n".join(index_rows) if index_rows else "| - | 0 | - |")
            + "\n"
        )

    if chinese:
        pages[home_path] = (
            _frontmatter("个人知识库", 0)
            + "# 个人知识库\n\n"
            + "## 一眼入口\n\n"
            + "- [[map/知识地图|知识地图]]\n"
            + "- 项目：从授权来源生成可读项目卡\n"
            + "- 学习：课程与学习资料的聚合入口\n"
            + "- [[_staging/00-待审核|待审核知识]]：AI 提案经人工批准后才进入正式知识层\n\n"
            + "## 已授权来源\n\n"
            + ("\n".join(source_links) if source_links else "尚未启用来源。")
            + "\n"
        )
        pages[map_path] = (
            _frontmatter("知识地图", 1)
            + "# 知识地图\n\n全局视图只突出 L0-L3；L4 局部主题和 L5 证据通过项目页进入。\n\n"
            + ("\n".join(item_links) if item_links else "暂无 L3 条目。")
            + "\n"
        )
    else:
        pages[home_path] = (
            _frontmatter("Personal Knowledge Vault", 0)
            + "# Personal Knowledge Vault\n\n"
            + "## Start here\n\n"
            + "- [[map/Knowledge Map|Knowledge map]]\n"
            + "- Projects: readable cards generated from authorized roots\n"
            + "- Learning: grouped course and learning materials\n"
            + "- [[_staging/00-Pending Review|Pending review]]: AI proposals require human promotion\n\n"
            + "## Authorized sources\n\n"
            + ("\n".join(source_links) if source_links else "No source is enabled.")
            + "\n"
        )
        pages[map_path] = (
            _frontmatter("Knowledge Map", 1)
            + "# Knowledge Map\n\nThe global view emphasizes L0-L3. Enter an item for L4 topics and L5 evidence.\n\n"
            + ("\n".join(item_links) if item_links else "No L3 item exists yet.")
            + "\n"
        )
    return dict(sorted(pages.items()))

