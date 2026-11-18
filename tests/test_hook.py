import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def child_env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(FIXTURES)])
    return env


def run_child(target: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "importsteady._child", target],
        capture_output=True,
        text=True,
        env=child_env(),
        timeout=120,
    )
    return proc.returncode, json.loads(proc.stdout.strip().splitlines()[-1])


def test_nested_self_time_is_not_absorbed_by_parent():
    rc, payload = run_child("fixturepkg")
    assert rc == 0, payload
    self_ns = payload["self_ns"]
    # slowmod sleeps 20 ms; its cost must show up on slowmod, not on fixturepkg.
    assert self_ns["fixturepkg.slowmod"] >= 15_000_000
    assert self_ns["fixturepkg"] < self_ns["fixturepkg.slowmod"]
    assert payload["total_ns"] >= self_ns["fixturepkg.slowmod"]
    # Nested package inside the fixture is recorded too.
    assert "fixturepkg.sub.leaf" in self_ns
    assert self_ns["fixturepkg.sub.leaf"] > 0


def test_preloaded_target_is_rejected_instead_of_silently_zero():
    rc, payload = run_child("os")
    assert rc == 1
    assert "already imported" in payload["error"]
    assert "total_ns" not in payload


def test_unknown_target_reports_error():
    rc, payload = run_child("definitely_not_a_real_module_123")
    assert rc == 1
    assert "ModuleNotFoundError" in payload["error"]
