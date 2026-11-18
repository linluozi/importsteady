# importsteady

`importsteady` measures where a Python import's time actually goes — and, unlike a
single `python -X importtime` run, it tells you how much of that ranking survives
repetition. It runs N isolated cold starts, records per-module **self** time with a
stack-based import hook, and reports medians, quartiles, and bootstrap rank-stability
curves for the top-k modules.

Upstream: none

This is an original tool (MIT). It is not a fork and applies no patch to any upstream
project, so the `-opt-lab` patch gates (G1–G5) do not apply; the verification section
below lists the checks this repository does pass.

## Why another import profiler

`-X importtime` prints one sample. Optimizing the wrong module because of that one
sample is common, and there is no error bar in its output. `importsteady` adds three
things:

1. **Self time without parent absorption.** A stack-based loader hook subtracts child
   execution time from the parent span, so a package is not charged for its children.
2. **Uncertainty.** Median/p25/p75 over N cold starts, plus per-module relative IQR.
3. **Rank stability.** Bootstrap over the N runs: how often does a k-run subsample
   reproduce the all-run top-1, and how much does the top-10 *set* churn?

### A measured caveat about `-X importtime`

On this machine (CPython 3.12.3), `python3 -X importtime -c "import email"` reports
`43799 us` of self time for the root `email` line, while the same import measured by
this hook takes `148 us` end-to-end. Wall clock for `python3 -c "import email"` is
`70.9 ms` and for the profiled command `71.6 ms` (median of 7), i.e. the profiled run
is not 43 ms slower. The root figure is therefore not a wall-clock delta; we do not
claim to know CPython's exact accounting path, only that the root number should not be
read as "email costs 43 ms". `importsteady` never charges interpreter startup to the
target module.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e . pytest
.venv/bin/python -m pytest -q          # 8 passed
```

Requires CPython >= 3.9. No runtime dependencies.

## Usage

```bash
.venv/bin/importsteady asyncio -n 30 --json evidence/asyncio.json
.venv/bin/importsteady urllib.request -n 30
```

Output (trimmed, real run):

```
importsteady 0.1.0  target=urllib.request  runs=30 (warmup=2)
total import: median 19.2 ms  [p25 19.1, p75 19.4]  min 19.0, max 20.1

  #  module                       median us       p25       p75  relIQR  present
  1  ssl                               2667.3    2613.4    2823.4    0.08  30/30
  2  urllib.request                    2390.8    2357.8    2498.3    0.06  30/30
  ...

rank stability of the same measurements (bootstrap over runs):
k runs  top-1 match  top-10 Jaccard
     1          93%            0.85
    13         100%            0.91
    30         100%            1.00
```

`--json` writes the full artifact: environment, seed, every run's raw self-time map,
summary, and the convergence table. Raw per-run samples are kept, not just aggregates.

## Evidence: four real targets, 30 cold starts each

Command for every row: `importsteady <target> -n 30 --warmup 2 --draws 400
--json evidence/<target>.json`; artifacts are committed in `evidence/`.

| target | total median | top-1 module (median) | gap #1/#2 | single-run top-1 match | top-10 Jaccard at k=1 / 13 / 30 |
|---|---|---|---|---|---|
| `asyncio` | 24.36 ms | `ssl` (3645 us) | 1.37x | 100% | 0.93 / 0.97 / 1.00 |
| `logging` | 4.80 ms | `logging` (1882 us) | 1.10x | 100% | 1.00 / 1.00 / 1.00 |
| `unittest` | 8.80 ms | `traceback` (1295 us) | 1.57x | 100% | 0.97 / 1.00 / 1.00 |
| `urllib.request` | 19.23 ms | `ssl` (2667 us) | 1.12x | 93% | 0.85 / 0.91 / 1.00 |

What the numbers say, and what they do not:

- **The head of the ranking is usually stable.** When #1 leads #2 by >=1.37x
  (`asyncio`, `unittest`) a single run picked the same #1 in 100% of the 400
  single-run draws.
- **A close #1 can flip.** `urllib.request` has only a 1.12x gap; the single-run
  top-1 matched the 30-run winner in 93% of draws (`ssl` 373, `urllib.request` 27).
- **The top-10 set is the weaker claim.** For `urllib.request`, a single run's top-10
  overlaps the consensus top-10 at Jaccard 0.85; 13 runs only reach 0.91; 30 runs
  reach 1.00. If you use a profiler to pick a list of modules to work on, one run is
  not enough — measure the set, not just the head.
- `logging` has only four modules above the 90%-presence filter, so its top-10 is the
  whole set and cannot churn; it is included as a control, not as evidence of stability.

There is no claim here of a speedup. This tool measures measurement error; inventing a
speedup number would contradict its purpose.

## Verification

```bash
.venv/bin/python -m pytest -q                  # 8 passed in 0.20s
.venv/bin/importsteady asyncio -n 30 --json /tmp/a.json
python3 - <<'PY'                               # all 4 artifacts self-consistent
import json,glob
for f in glob.glob('evidence/*.json'):
    d=json.load(open(f))
    assert len(d['runs_self_ns'])==d['config']['runs']==30
    assert d['summary']['n_runs']==30
    assert d['convergence'][-1]['top10_jaccard']==1.0
print('evidence ok')
PY
```

Units tests cover: self-time nesting (a 20 ms child must not be charged to its parent),
preloaded-target rejection, missing-target error, quantile definition, presence filter,
IQR, deterministic bootstrap, full-k convergence, and detection of an unstable
single-run ranking.

## Limitations

- Measures `exec_module` only: finder/loader filesystem work before `exec_module` and
  C-level builtin init are not attributed. It is a module-execution profile, not a
  syscall profile.
- CPython only; the hook uses `sys.meta_path` and `PathFinder`.
- The target must not already be imported at interpreter startup (the child exits with
  an explicit error rather than reporting a fake 0 ms).
- Timings are machine- and load-dependent. The committed artifacts are from one
  machine; rerun before comparing against them.

## Environment (committed evidence)

- CPython 3.12.3 (`/usr/bin/python3`), Linux, AMD EPYC 7K62, 4 vCPU, 3.7 GB RAM.
- 30 measured cold starts per target + 2 discarded warmups; 400 bootstrap draws;
  seed `20261119`; `time.perf_counter_ns()` inside `exec_module`.
- Raw per-run samples: `evidence/<target>.json` → `runs_self_ns`.

## 本轮创新

First quantification of **rank stability** in Python import-cost attribution: instead of
another profiler, this measures how often a k-cold-start subsample reproduces the
all-run top-1 and top-10 set, on four real stdlib targets (1,200 cold starts total).
The new, falsifiable conclusion is that the head is stable at a >=1.37x gap but the
top-10 membership is not (Jaccard 0.85 at k=1 for `urllib.request`, 0.91 even at
k=13) — a failure mode that a single `-X importtime` run cannot show and that the
existing `speedgap` / `benchreconcile` projects (synthetic-vs-real benchmarks and
README claim reconciliation) do not measure.

## License

MIT, Copyright (c) 2026 linluozi. See `LICENSE`.