"""Spawn isolated cold starts and collect per-module self times."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time

from importsteady import stats

PACKAGE_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    old = env.get("PYTHONPATH")
    env["PYTHONPATH"] = PACKAGE_PARENT + (os.pathsep + old if old else "")
    # Keep the child's own import cost from being polluted by user site config.
    env.pop("PYTHONSTARTUP", None)
    return env


def run_once(target: str, timeout: float = 120.0, python: str | None = None) -> dict:
    cmd = [python or sys.executable, "-m", "importsteady._child", target]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, env=child_env()
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if not lines:
        raise RuntimeError(
            f"child produced no output for {target!r} (rc={proc.returncode}): "
            f"{proc.stderr[-400:]}"
        )
    payload = json.loads(lines[-1])
    if "error" in payload:
        raise RuntimeError(f"import {target!r} failed: {payload['error']}")
    payload["command"] = cmd
    return payload


def cpu_model() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def profile(
    target: str,
    runs: int = 30,
    warmup: int = 2,
    draws: int = 300,
    seed: int = 20261119,
    timeout: float = 120.0,
) -> dict:
    if runs < 1:
        raise ValueError("runs must be >= 1")
    if warmup < 0:
        raise ValueError("warmup must be >= 0")

    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    warm = []
    for _ in range(warmup):
        warm.append(run_once(target, timeout=timeout))
    raw = [run_once(target, timeout=timeout) for _ in range(runs)]

    per_run = [r["self_ns"] for r in raw]
    totals = [r["total_ns"] for r in raw]
    summary = stats.summarize(per_run)
    sizes = [k for k in (1, 2, 3, 5, 8, 13, 21, 30, 50) if k <= runs]
    if sizes[-1] != runs:
        sizes.append(runs)
    conv = stats.convergence(per_run, sizes, draws=draws, seed=seed)

    single = next((row["single_run_top1"] for row in conv if row["k"] == 1), {})
    total_sorted = sorted(totals)
    return {
        "schema": "importsteady/1",
        "target": target,
        "started_utc": started,
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "cpu": cpu_model(),
            "executable": sys.executable,
        },
        "config": {
            "runs": runs,
            "warmup": warmup,
            "draws": draws,
            "seed": seed,
            "timeout_s": timeout,
            "command": f"{sys.executable} -m importsteady._child {target}",
            "timer": "time.perf_counter_ns inside exec_module",
        },
        "warmup_totals_ns": [r["total_ns"] for r in warm],
        "total_ms": {
            "median": stats.quantile(total_sorted, 0.5) / 1e6,
            "p25": stats.quantile(total_sorted, 0.25) / 1e6,
            "p75": stats.quantile(total_sorted, 0.75) / 1e6,
            "min": total_sorted[0] / 1e6,
            "max": total_sorted[-1] / 1e6,
        },
        "runs_self_ns": per_run,
        "runs_total_ns": totals,
        "summary": summary,
        "convergence": conv,
        "min_k_top1_90pct": stats.minimal_k(conv, 0.9),
        "single_run_top1_counts": single,
    }
