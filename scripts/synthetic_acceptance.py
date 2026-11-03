#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import threading
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from personal_vault.config import load_config, write_config_atomic  # noqa: E402
from personal_vault.integrations import doctor, run_restic_backup  # noqa: E402
from personal_vault.paths import VaultPaths  # noqa: E402
from personal_vault.proposals import stage_proposals  # noqa: E402
from personal_vault.review import promote_proposal  # noqa: E402
from personal_vault.search import search_vault  # noqa: E402
from personal_vault.setup import initialize  # noqa: E402
from personal_vault.sources import add_source, enable_source  # noqa: E402
from personal_vault.status import collect_status  # noqa: E402
from personal_vault.update import run_update  # noqa: E402
from personal_vault.web_actions import WebActionService  # noqa: E402
from personal_vault.webapp import create_server  # noqa: E402


@dataclass
class CommandResult:
    returncode: int = 0
    stdout: str = '{"message_type":"summary","snapshot_id":"synthetic-snapshot-001"}\n'
    stderr: str = ""


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _vault_contains(vault: Path, value: str) -> bool:
    for path in vault.rglob("*.md"):
        try:
            if value in path.read_text(encoding="utf-8"):
                return True
        except (OSError, UnicodeError):
            continue
    return False


def run_acceptance(workspace: Path) -> dict[str, object]:
    workspace = workspace.expanduser().resolve(strict=False)
    if workspace.exists() and any(workspace.iterdir()):
        raise RuntimeError("WORKSPACE_NOT_EMPTY")
    workspace.mkdir(parents=True, exist_ok=True)
    projects = workspace / "AuthorizedProjects"
    learning = workspace / "AuthorizedLearning"
    project = projects / "flight-controller"
    course = learning / "linear-algebra"
    project.mkdir(parents=True)
    course.mkdir(parents=True)
    (project / "README.md").write_text(
        "# Flight Controller\n\nA synthetic control project with auditable decisions.\n",
        encoding="utf-8",
    )
    synthetic_secret = "gh" + "p_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890ab"
    (project / ".env").write_text(f"TOKEN={synthetic_secret}\n", encoding="utf-8")
    (course / "README.md").write_text(
        "# Linear Algebra\n\nA synthetic learning track about matrices and state estimation.\n",
        encoding="utf-8",
    )

    paths = VaultPaths.from_roots(workspace / "Vault", workspace / "Data")
    initialize(paths=paths, language="zh-CN", repo_root=ROOT)
    config_path = Path(paths.config)
    add_source(config_path, source_id="projects", kind="project", path=projects)
    add_source(config_path, source_id="learning", kind="learning", path=learning)
    enable_source(config_path, "projects", confirmation="ENABLE:projects")
    enable_source(config_path, "learning", confirmation="ENABLE:learning")

    preview = run_update(config_path, apply=False)
    preview_wrote_nothing = not Path(paths.vault).joinpath("00-首页.md").exists()
    applied = run_update(config_path, apply=True)
    repeated = run_update(config_path, apply=True)

    proposal_input = workspace / "proposal.json"
    proposal_input.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "proposals": [
                    {
                        "id": "audit-before-automation",
                        "title": "自动化前先建立审计基线",
                        "summary": "先记录可验证状态，再启用每日自动化。",
                        "body": "对输入、输出和确认点建立基线，可降低自动更新掩盖变化的风险。",
                        "knowledge_type": "lesson",
                        "target": "knowledge",
                        "source_refs": [{"source_id": "projects", "record_id": "flight-controller/README.md"}],
                        "confidence": 0.91,
                        "sensitivity": "normal",
                    }
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    stage_preview = stage_proposals(config_path, proposal_input, dry_run=True)
    staging_path = Path(paths.vault) / "_staging" / "audit-before-automation.md"
    staging_preview_wrote_nothing = not staging_path.exists()
    staged = stage_proposals(config_path, proposal_input, dry_run=False)
    staging_created = staging_path.is_file()
    promoted = promote_proposal(
        config_path,
        "audit-before-automation",
        confirmation="PROMOTE:audit-before-automation",
    )
    search_results = search_vault(paths.vault, "审计 基线")

    server = create_server("127.0.0.1", 0, service=WebActionService(config_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = int(server.server_address[1])
        with urlopen(f"http://127.0.0.1:{port}/api/status", timeout=10) as response:
            web_payload = json.loads(response.read().decode("utf-8"))
            csp = response.headers.get("Content-Security-Policy", "")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)

    restic = workspace / ("restic.exe" if os.name == "nt" else "restic")
    restic.write_text("synthetic executable placeholder\n", encoding="utf-8")
    if os.name == "posix":
        restic.chmod(0o700)
    config = load_config(config_path)
    config["integrations"]["restic"] = {
        "enabled": True,
        "repository": str(workspace / "EncryptedBackupFixture"),
        "executable": str(restic),
    }
    write_config_atomic(config_path, config)
    previous_password = os.environ.get("RESTIC_PASSWORD")
    os.environ["RESTIC_PASSWORD"] = "synthetic-only"
    try:
        backup_preview = run_restic_backup(config_path, apply=False, runner=lambda *_args, **_kwargs: CommandResult())
        backup = run_restic_backup(config_path, apply=True, runner=lambda *_args, **_kwargs: CommandResult())
    finally:
        if previous_password is None:
            os.environ.pop("RESTIC_PASSWORD", None)
        else:
            os.environ["RESTIC_PASSWORD"] = previous_password

    snapshot = workspace / "SyntheticSnapshot" / "Vault"
    shutil.copytree(Path(paths.vault), snapshot)
    restored = workspace / "RestoredVault"
    shutil.copytree(snapshot, restored)
    status = collect_status(config_path)
    health = doctor(config_path)
    checks = {
        "preview_read_only": preview["applied"] is False and preview_wrote_nothing,
        "deterministic_apply": applied["applied"] is True and applied["created"] > 0,
        "idempotent_second_run": repeated["created"] == 0 and repeated["updated"] == 0 and repeated["removed"] == 0,
        "forbidden_secret_excluded": applied["excluded"] >= 1 and not _vault_contains(Path(paths.vault), synthetic_secret),
        "staging_preview_read_only": stage_preview["dry_run"] is True and staging_preview_wrote_nothing,
        "proposal_staged": staged["created"] == 1 and staging_created,
        "proposal_promoted": promoted["status"] == "approved" and promoted["changed"] is True and not staging_path.exists(),
        "reviewed_search": any(item["path"].startswith("knowledge/") for item in search_results),
        "localhost_ui": web_payload["language"] == "zh-CN" and "unsafe-inline" not in csp and "frame-ancestors 'none'" in csp,
        "core_doctor": health["ok"] is True,
        "backup_preview_read_only": backup_preview["applied"] is False,
        "backup_adapter": backup["snapshot_id"] == "synthetic-snapshot-001",
        "synthetic_restore": _tree_hash(Path(paths.vault)) == _tree_hash(restored),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "metrics": {
            "sources": status["sources"]["total"],
            "formal_pages": status["vault"]["formal_pages"],
            "approved": status["proposals"]["approved"],
            "backup_snapshot": backup["snapshot_id"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an offline synthetic end-to-end acceptance exercise.")
    parser.add_argument("--workspace", required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        report = run_acceptance(arguments.workspace)
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}:{exc}"}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
