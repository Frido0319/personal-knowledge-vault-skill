# Changelog

All notable changes to this project are documented here.

## 0.1.1 - 2026-11-04

### Fixed

- Generate the release wheel with the standard library instead of environment-specific build backends.
- Store wheel and Skill ZIP entries without compression so identical source commits are byte-for-byte reproducible across supported Python environments.
- Validate native Windows paths, scheduler output, permissions, and release dependencies in CI.

## 0.1.0 - 2026-11-04

### Added

- Local-first Linux and native Windows runtime with explicit source authorization.
- Human-readable L0-L5 Obsidian vault generation and idempotent manifests.
- Human-reviewed semantic staging, offline search, status, and bilingual localhost console.
- Optional QMD, Restic, and strictly private GitHub mirror adapters.
- Native systemd user and Windows Task Scheduler maintenance.
- Reusable `build-personal-knowledge-vault` Skill with hash-verified bundled runtime installation.
- Reproducible wheel and `.skill` builds, public-tree privacy audit, synthetic recovery exercise, and Ubuntu/Windows CI.
