"""Controlled injection experiment: how many cold starts to detect a known regression?

Ground truth: a fixture package with six modules of comparable import cost.  One
module gets ``time.sleep(delta)`` added to its body, so the true cost difference is
exactly ``delta`` microseconds.  For every delta we run ``runs`` cold starts per trial
and reuse the first k of them, then check whether the injected module is the median
self-time winner.  Detection rate over trials is the empirical power of the method.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
import shutil
import statistics
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from importsteady.profile import run_once  # noqa: E402

BODY = """import time

x = 0
for i in range(4000):
    x += i * i
VALUE = x
"""


def build(root: pathlib.Path, delta_us: int, injected: int = 2) -> None:
    pkg = root / "injpkg"
    pkg.mkdir(parents=True)
    for i in range(6):
        body = BODY
        if i == injected and delta_us > 0:
            body = f"import time\ntime.sleep({delta_us / 1e6})\n" + body
        (pkg / f"m{i}.py").write_text(body, encoding="utf-8")
    (pkg / "__init__.py").write_text(
        "".join(f"from . import m{i}\n" for i in range(6)), encoding="utf-8"
    )


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval for a binomial rate."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def medians(runs: list[dict], names: list[str]) -> dict[str, float]:
    return {
        name: statistics.median(run[name] for run in runs if name in run)
        for name in names
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--deltas", default="0,25,50,100,200")
    ap.add_argument("--out", default="evidence/injection.json")
    args = ap.parse_args()
    deltas = [int(x) for x in args.deltas.split(",")]
    ks = [k for k in (1, 2, 3, 5, 10) if k <= args.runs]
    names = [f"injpkg.m{i}" for i in range(6)]
    injected = "injpkg.m2"
    seed = 20261119
    rng = random.Random(seed)
    result = {
        "schema": "importsteady/injection/1",
        "seed": seed,
        "trials": args.trials,
        "runs_per_trial": args.runs,
        "ks": ks,
        "injected_module": injected,
        "baseline_modules": names,
        "note": "no warmup between trials; first run of a trial can be colder",
        "results": {},
    }
    for delta in deltas:
        root = pathlib.Path(tempfile.mkdtemp(prefix="importsteady-inj-"))
        try:
            build(root, delta)
            os.environ["PYTHONPATH"] = str(root)
            det = {k: 0 for k in ks}
            ranks = {k: [] for k in ks}
            trials = []
            for _ in range(args.trials):
                runs = [run_once("injpkg")["self_ns"] for _ in range(args.runs)]
                med_all = medians(runs, names)
                for k in ks:
                    med = medians(runs[:k], names)
                    ordered = sorted(names, key=lambda n: (-med[n], n))
                    det[k] += ordered[0] == injected
                    ranks[k].append(ordered.index(injected) + 1)
                trials.append(
                    {"winner_all": min(names, key=lambda n: (-med_all[n], n))}
                )
            result["results"][str(delta)] = {
                "detection_rate": {str(k): det[k] / args.trials for k in ks},
                "detection_rate_ci95": {
                    str(k): list(wilson(det[k], args.trials)) for k in ks
                },
                "median_rank_of_injected": {
                    str(k): statistics.median(ranks[k]) for k in ks
                },
                "all_runs_winner_counts": {
                    w: sum(1 for t in trials if t["winner_all"] == w)
                    for w in sorted({t["winner_all"] for t in trials})
                },
            }
            print(delta, result["results"][str(delta)]["detection_rate"], flush=True)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())