import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def test_cli_writes_reproducible_json(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(FIXTURES)])
    out = tmp_path / "run.json"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "importsteady.cli",
            "fixturepkg",
            "-n",
            "3",
            "--warmup",
            "0",
            "--draws",
            "20",
            "--seed",
            "11",
            "--json",
            str(out),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text())
    assert data["schema"] == "importsteady/1"
    assert data["config"]["runs"] == 3
    assert data["config"]["seed"] == 11
    assert len(data["runs_self_ns"]) == 3
    assert len(data["convergence"]) >= 1
    assert data["summary"]["modules"][0]["module"].startswith("fixturepkg")
    assert "runs needed for" in proc.stdout
