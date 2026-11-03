from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_acceptance_covers_full_local_product_loop(tmp_path: Path) -> None:
    workspace = tmp_path / "acceptance"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "synthetic_acceptance.py"),
            "--workspace",
            str(workspace),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["checks"] and all(report["checks"].values())
    assert report["metrics"]["sources"] == 2
    assert report["metrics"]["approved"] == 1
    assert report["metrics"]["backup_snapshot"] == "synthetic-snapshot-001"
