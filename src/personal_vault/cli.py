from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .paths import VaultPaths, default_paths
from .proposals import list_proposals, stage_proposals
from .review import promote_proposal, reject_proposal
from .scheduler import install_schedule, remove_schedule
from .config import load_config
from .integrations import doctor, run_qmd_update, run_restic_backup
from .github import prepare_private_mirror, publish_private_mirror
from .search import search_vault
from .setup import initialize
from .skill_catalog import add_github_skill, build_skill_catalog, list_github_skills
from .sources import add_source, disable_source, enable_source, list_sources
from .status import collect_status, format_status_text
from .update import run_update
from .web_actions import WebActionService
from .webapp import run_server


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    defaults = default_paths()
    parser = argparse.ArgumentParser(prog="personal-vault")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="initialize an empty private vault")
    init.add_argument("--vault", type=Path, default=Path(defaults.vault))
    init.add_argument("--data", type=Path, default=Path(defaults.data))
    init.add_argument("--language", choices=("zh-CN", "en"), default="zh-CN")
    init.add_argument("--dry-run", action="store_true")

    source = commands.add_parser("source", help="manage explicit source authorization")
    source_actions = source.add_subparsers(dest="source_action", required=True)
    for name in ("add", "list", "enable", "disable"):
        sub = source_actions.add_parser(name)
        sub.add_argument("--config", required=True, type=Path)
        if name != "list":
            sub.add_argument("--id", required=True)
        if name == "add":
            sub.add_argument("--kind", required=True)
            sub.add_argument("--path", required=True, type=Path)
        if name == "enable":
            sub.add_argument("--confirmation", required=True)

    update = commands.add_parser("update", help="preview or apply deterministic knowledge updates")
    update.add_argument("--config", required=True, type=Path)
    update_mode = update.add_mutually_exclusive_group(required=True)
    update_mode.add_argument("--preview", action="store_true")
    update_mode.add_argument("--apply", action="store_true")

    stage = commands.add_parser("stage", help="manage semantic knowledge proposals")
    stage_actions = stage.add_subparsers(dest="stage_action", required=True)
    stage_add = stage_actions.add_parser("add")
    stage_add.add_argument("--config", required=True, type=Path)
    stage_add.add_argument("--input", required=True, type=Path)
    stage_add.add_argument("--dry-run", action="store_true")
    stage_list = stage_actions.add_parser("list")
    stage_list.add_argument("--config", required=True, type=Path)

    review = commands.add_parser("review", help="promote or reject staged knowledge")
    review_actions = review.add_subparsers(dest="review_action", required=True)
    for name in ("promote", "reject"):
        sub = review_actions.add_parser(name)
        sub.add_argument("--config", required=True, type=Path)
        sub.add_argument("--id", required=True)
        sub.add_argument("--confirmation", required=True)

    search = commands.add_parser("search", help="search reviewed and generated knowledge")
    search.add_argument("--config", required=True, type=Path)
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=20)

    status = commands.add_parser("status", help="show a read-only system snapshot")
    status.add_argument("--config", required=True, type=Path)
    status.add_argument("--format", choices=("json", "text"), default="text")

    doctor_command = commands.add_parser("doctor", help="check core and optional dependencies")
    doctor_command.add_argument("--config", required=True, type=Path)

    index = commands.add_parser("index", help="manage optional local indexes")
    index_actions = index.add_subparsers(dest="index_action", required=True)
    qmd = index_actions.add_parser("qmd")
    qmd.add_argument("--config", required=True, type=Path)
    qmd_mode = qmd.add_mutually_exclusive_group(required=True)
    qmd_mode.add_argument("--preview", action="store_true")
    qmd_mode.add_argument("--apply", action="store_true")

    backup = commands.add_parser("backup", help="run optional encrypted backups")
    backup_actions = backup.add_subparsers(dest="backup_action", required=True)
    restic = backup_actions.add_parser("restic")
    restic.add_argument("--config", required=True, type=Path)
    restic_mode = restic.add_mutually_exclusive_group(required=True)
    restic_mode.add_argument("--preview", action="store_true")
    restic_mode.add_argument("--apply", action="store_true")

    schedule = commands.add_parser("schedule", help="manage native daily maintenance")
    schedule_actions = schedule.add_subparsers(dest="schedule_action", required=True)
    schedule_show = schedule_actions.add_parser("show")
    schedule_show.add_argument("--config", required=True, type=Path)
    for name in ("install", "remove"):
        sub = schedule_actions.add_parser(name)
        sub.add_argument("--config", required=True, type=Path)
        mode = sub.add_mutually_exclusive_group(required=True)
        mode.add_argument("--preview", action="store_true")
        mode.add_argument("--apply", action="store_true")

    skill = commands.add_parser("skill", help="catalog authored and adopted GitHub Skills")
    skill_actions = skill.add_subparsers(dest="skill_action", required=True)
    skill_add = skill_actions.add_parser("add")
    skill_add.add_argument("--config", required=True, type=Path)
    skill_add.add_argument("--repository", required=True)
    skill_add.add_argument("--ownership", required=True, choices=("authored", "maintained", "vendored"))
    skill_add.add_argument("--commit", required=True)
    skill_add.add_argument("--skill-path", default="SKILL.md")
    skill_add.add_argument("--summary", default="")
    skill_list = skill_actions.add_parser("list")
    skill_list.add_argument("--config", required=True, type=Path)
    skill_catalog = skill_actions.add_parser("catalog")
    skill_catalog.add_argument("--config", required=True, type=Path)
    skill_mode = skill_catalog.add_mutually_exclusive_group(required=True)
    skill_mode.add_argument("--preview", action="store_true")
    skill_mode.add_argument("--apply", action="store_true")

    github = commands.add_parser("github", help="prepare or publish a strictly private mirror")
    github_actions = github.add_subparsers(dest="github_action", required=True)
    github_prepare = github_actions.add_parser("prepare")
    github_prepare.add_argument("--config", required=True, type=Path)
    github_mode = github_prepare.add_mutually_exclusive_group(required=True)
    github_mode.add_argument("--preview", action="store_true")
    github_mode.add_argument("--apply", action="store_true")
    github_publish = github_actions.add_parser("publish")
    github_publish.add_argument("--config", required=True, type=Path)
    github_publish.add_argument("--confirmation", required=True)

    serve = commands.add_parser("serve", help="run the localhost management console")
    serve.add_argument("--config", required=True, type=Path)
    serve.add_argument("--host", choices=("127.0.0.1", "localhost", "::1"), default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8766)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "init":
            result = initialize(
                paths=VaultPaths.from_roots(arguments.vault, arguments.data),
                language=arguments.language,
                dry_run=arguments.dry_run,
            )
        elif arguments.command == "update":
            result = run_update(arguments.config, apply=arguments.apply)
        elif arguments.command == "source":
            if arguments.source_action == "add":
                result = add_source(
                    arguments.config,
                    source_id=arguments.id,
                    kind=arguments.kind,
                    path=arguments.path,
                )
            elif arguments.source_action == "enable":
                result = enable_source(arguments.config, arguments.id, confirmation=arguments.confirmation)
            elif arguments.source_action == "disable":
                result = disable_source(arguments.config, arguments.id)
            else:
                result = list_sources(arguments.config)
        elif arguments.command == "stage":
            if arguments.stage_action == "add":
                result = stage_proposals(arguments.config, arguments.input, dry_run=arguments.dry_run)
            else:
                result = list_proposals(arguments.config)
        elif arguments.command == "review":
            if arguments.review_action == "promote":
                result = promote_proposal(arguments.config, arguments.id, confirmation=arguments.confirmation)
            else:
                result = reject_proposal(arguments.config, arguments.id, confirmation=arguments.confirmation)
        elif arguments.command == "search":
            config = load_config(arguments.config)
            result = search_vault(config["vault"], arguments.query, limit=arguments.limit)
        elif arguments.command == "status":
            result = collect_status(arguments.config)
            if arguments.format == "text":
                print(format_status_text(result))
                return 0
        elif arguments.command == "doctor":
            result = doctor(arguments.config)
        elif arguments.command == "index":
            result = run_qmd_update(arguments.config, apply=arguments.apply)
        elif arguments.command == "backup":
            result = run_restic_backup(arguments.config, apply=arguments.apply)
        elif arguments.command == "schedule":
            if arguments.schedule_action == "remove":
                result = remove_schedule(arguments.config, apply=arguments.apply)
            else:
                result = install_schedule(
                    arguments.config,
                    apply=arguments.schedule_action == "install" and arguments.apply,
                )
        elif arguments.command == "skill":
            if arguments.skill_action == "add":
                result = add_github_skill(
                    arguments.config,
                    repository=arguments.repository,
                    ownership=arguments.ownership,
                    commit=arguments.commit,
                    skill_path=arguments.skill_path,
                    summary=arguments.summary,
                )
            elif arguments.skill_action == "catalog":
                result = build_skill_catalog(arguments.config, apply=arguments.apply)
            else:
                result = list_github_skills(arguments.config)
        elif arguments.command == "github":
            if arguments.github_action == "prepare":
                result = prepare_private_mirror(arguments.config, apply=arguments.apply)
            else:
                result = publish_private_mirror(
                    arguments.config,
                    confirmation=arguments.confirmation,
                )
        elif arguments.command == "serve":
            run_server(
                arguments.host,
                arguments.port,
                service=WebActionService(arguments.config),
            )
            return 0
        else:
            raise ValueError("UNSUPPORTED_COMMAND")
    except (OSError, ValueError, RuntimeError) as exc:
        _print({"error": str(exc)})
        return 1
    _print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
