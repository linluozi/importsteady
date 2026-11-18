"""Aggregation and rank-stability statistics for repeated cold starts."""

from __future__ import annotations

import math
import random
from typing import Iterable, Sequence


def quantile(sorted_vals: Sequence[float], q: float) -> float:
    """Linear-interpolation quantile (same definition as numpy's default)."""
    if not sorted_vals:
        raise ValueError("empty sample")
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = (len(sorted_vals) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(sorted_vals[lo])
    frac = pos - lo
    return float(sorted_vals[lo]) * (1.0 - frac) + float(sorted_vals[hi]) * frac


def _medians(runs: Sequence[dict[str, int]]) -> dict[str, float]:
    samples: dict[str, list[int]] = {}
    for run in runs:
        for name, ns in run.items():
            samples.setdefault(name, []).append(ns)
    out = {}
    for name, vals in samples.items():
        vals = sorted(vals)
        out[name] = quantile(vals, 0.5)
    return out


def summarize(runs: Sequence[dict[str, int]], min_presence: float = 0.9) -> dict:
    """Per-module median/p25/p75 self time in microseconds."""
    if not runs:
        raise ValueError("no runs")
    n = len(runs)
    needed = max(1, math.ceil(n * min_presence))
    samples: dict[str, list[int]] = {}
    for run in runs:
        for name, ns in run.items():
            samples.setdefault(name, []).append(ns)
    modules = []
    for name, vals in samples.items():
        if len(vals) < needed:
            continue
        vals = sorted(vals)
        modules.append(
            {
                "module": name,
                "runs_present": len(vals),
                "median_us": quantile(vals, 0.5) / 1000.0,
                "p25_us": quantile(vals, 0.25) / 1000.0,
                "p75_us": quantile(vals, 0.75) / 1000.0,
                "min_us": vals[0] / 1000.0,
                "max_us": vals[-1] / 1000.0,
            }
        )
    modules.sort(key=lambda m: (-m["median_us"], m["module"]))
    for m in modules:
        med = m["median_us"]
        m["rel_iqr"] = (m["p75_us"] - m["p25_us"]) / med if med else 0.0
    return {"n_runs": n, "modules": modules}


def top_names(medians: dict[str, float], k: int) -> list[str]:
    return [name for name, _ in sorted(medians.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]


def convergence(
    runs: Sequence[dict[str, int]],
    sizes: Iterable[int],
    draws: int = 300,
    seed: int = 20261119,
    top_k: int = 10,
) -> list[dict]:
    """How often a k-run subsample reproduces the all-runs ranking.

    For every k we draw ``draws`` subsets of k distinct runs (without
    replacement) and compare the median-based top-1 and top-k sets with the
    reference computed from every run.  Deterministic for a given seed.
    """
    if not runs:
        raise ValueError("no runs")
    n = len(runs)
    ref_medians = _medians(runs)
    ref_top1 = top_names(ref_medians, 1)[0] if ref_medians else None
    ref_topk = set(top_names(ref_medians, top_k))
    rng = random.Random(seed)
    rows = []
    for k in sizes:
        if k < 1 or k > n:
            continue
        hit1 = 0
        jaccard = 0.0
        single_top1: dict[str, int] = {}
        for _ in range(draws):
            idx = rng.sample(range(n), k)
            med = _medians([runs[i] for i in idx])
            t1 = top_names(med, 1)[0] if med else None
            if t1 == ref_top1:
                hit1 += 1
            if k == 1:
                single_top1[t1] = single_top1.get(t1, 0) + 1
            cur = set(top_names(med, top_k))
            union = cur | ref_topk
            jaccard += len(cur & ref_topk) / len(union) if union else 1.0
        rows.append(
            {
                "k": k,
                "top1_agreement": hit1 / draws,
                f"top{top_k}_jaccard": jaccard / draws,
                "single_run_top1": single_top1 if k == 1 else None,
            }
        )
    return rows


def minimal_k(rows: Sequence[dict], target: float = 0.9) -> int | None:
    """Smallest k whose top-1 agreement reaches ``target``."""
    for row in rows:
        if row["top1_agreement"] >= target:
            return int(row["k"])
    return None
