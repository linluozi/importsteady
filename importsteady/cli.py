"""Command line interface for importsteady."""

from __future__ import annotations

import argparse
import json
import sys

from importsteady import __version__
from importsteady.profile import profile


def _fmt(value: float) -> str:
    return f"{value:.1f}"


def render(result: dict, top: int = 15) -> str:
    lines = []
    lines.append(
        f"importsteady {__version__}  target={result['target']}  "
        f"runs={result['config']['runs']} (warmup={result['config']['warmup']})"
    )
    env = result["environment"]
    lines.append(f"python {env['python']}  {env['cpu']}")
    total = result["total_ms"]
    lines.append(
        f"total import: median {_fmt(total['median'])} ms  "
        f"[p25 {_fmt(total['p25'])}, p75 {_fmt(total['p75'])}]  "
        f"min {_fmt(total['min'])}, max {_fmt(total['max'])}"
    )
    lines.append("")
    lines.append(f"{'#':>3}  {'module':<34} {'median us':>10} {'p25':>9} {'p75':>9} {'relIQR':>7}  present")
    for i, mod in enumerate(result["summary"]["modules"][:top], 1):
        lines.append(
            f"{i:>3}  {mod['module']:<34} {_fmt(mod['median_us']):>10} "
            f"{_fmt(mod['p25_us']):>9} {_fmt(mod['p75_us']):>9} "
            f"{mod['rel_iqr']:>7.2f}  {mod['runs_present']}/{result['config']['runs']}"
        )
    lines.append("")
    lines.append("rank stability of the same measurements (bootstrap over runs):")
    lines.append(f"{'k runs':>6}  {'top-1 match':>11}  {'top-10 Jaccard':>14}")
    for row in result["convergence"]:
        lines.append(
            f"{row['k']:>6}  {row['top1_agreement']:>11.0%}  "
            f"{row['top10_jaccard'] if 'top10_jaccard' in row else row.get('top10_jaccard', 0):>14.2f}"
        )
    single = result.get("single_run_top1_counts") or {}
    if single:
        total_draws = sum(single.values())
        pick, count = max(single.items(), key=lambda kv: kv[1])
        winner = result["summary"]["modules"][0]["module"]
        lines.append("")
        lines.append(
            f"single-run top-1 pick: {pick!r} in {count}/{total_draws} draws "
            f"({count / total_draws:.0%}); all-run winner: {winner!r}"
        )
    need = result.get("min_k_top1_90pct")
    if need:
        lines.append(f"runs needed for >=90% top-1 agreement: {need}")
    else:
        lines.append("runs needed for >=90% top-1 agreement: not reached")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="importsteady",
        description="Measure stable per-module import cost over repeated cold starts.",
    )
    parser.add_argument("target", help="importable module or package name")
    parser.add_argument("-n", "--runs", type=int, default=30, help="cold starts (default 30)")
    parser.add_argument("--warmup", type=int, default=2, help="discarded cold starts (default 2)")
    parser.add_argument("--draws", type=int, default=300, help="bootstrap draws (default 300)")
    parser.add_argument("--seed", type=int, default=20261119)
    parser.add_argument("--json", metavar="PATH", help="write the full artifact here")
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)

    try:
        result = profile(
            args.target,
            runs=args.runs,
            warmup=args.warmup,
            draws=args.draws,
            seed=args.seed,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"importsteady: {exc}", file=sys.stderr)
        return 2

    print(render(result, top=args.top))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
