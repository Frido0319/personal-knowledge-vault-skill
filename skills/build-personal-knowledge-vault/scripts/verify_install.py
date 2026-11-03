#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def _venv_python(target: Path) -> Path:
    return target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _check(argv: list[str]) -> dict[str, object]:
    result = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=120)
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def verify(python: Path, config: Path | None = None) -> dict[str, object]:
    checks = {
        "imports": _check([str(python), "-c", "import personal_vault, yaml"]),
        "cli": _check([str(python), "-m", "personal_vault.cli", "--help"]),
    }
    if config is not None:
        checks["doctor"] = _check(
            [str(python), "-m", "personal_vault.cli", "doctor", "--config", str(config)]
        )
    return {"ok": all(bool(item["ok"]) for item in checks.values()), "python": str(python), "checks": checks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify an isolated Personal Knowledge Vault runtime.")
    location = parser.add_mutually_exclusive_group(required=True)
    location.add_argument("--target", type=Path)
    location.add_argument("--python", type=Path)
    parser.add_argument("--config", type=Path)
    arguments = parser.parse_args(argv)
    python = arguments.python or _venv_python(arguments.target.expanduser())
    try:
        result = verify(python.expanduser(), arguments.config)
    except (OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
