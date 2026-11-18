import pytest

from importsteady import stats


def test_quantile_matches_linear_interpolation():
    vals = [1.0, 2.0, 3.0, 4.0]
    assert stats.quantile(vals, 0.0) == 1.0
    assert stats.quantile(vals, 0.5) == 2.5
    assert stats.quantile(vals, 1.0) == 4.0
    assert stats.quantile([7.0], 0.9) == 7.0
    with pytest.raises(ValueError):
        stats.quantile([], 0.5)


def make_runs(spec, repeats=10):
    """spec: module -> ns per run; every run contains every module."""
    return [{name: ns for name, ns in spec.items()} for _ in range(repeats)]


def test_summarize_orders_by_median_and_drops_rare_modules():
    runs = make_runs({"a": 1000, "b": 3000, "c": 2000}, repeats=10)
    runs[0]["rare"] = 99999  # present in 1/10 runs -> below 90% presence
    summary = stats.summarize(runs)
    names = [m["module"] for m in summary["modules"]]
    assert names == ["b", "c", "a"]
    assert all(m["module"] != "rare" for m in summary["modules"])
    assert summary["n_runs"] == 10
    assert summary["modules"][0]["median_us"] == pytest.approx(3.0)


def test_summarize_reports_iqr():
    runs = [{f"m{i}": (i + 1) * 1000 for i in range(10)} for _ in range(12)]
    # one module with a wide spread
    for i, run in enumerate(runs):
        run["noisy"] = 1000 if i % 2 else 5000
    summary = stats.summarize(runs)
    noisy = next(m for m in summary["modules"] if m["module"] == "noisy")
    assert noisy["p25_us"] < noisy["median_us"] < noisy["p75_us"]
    assert noisy["rel_iqr"] > 0.5


def test_convergence_is_deterministic_and_reaches_one_at_full_k():
    runs = make_runs({"big": 5000, "mid": 3000, "small": 1000}, repeats=12)
    a = stats.convergence(runs, [1, 3, 12], draws=50, seed=7)
    b = stats.convergence(runs, [1, 3, 12], draws=50, seed=7)
    assert a == b
    assert a[-1]["k"] == 12
    assert a[-1]["top1_agreement"] == 1.0
    assert stats.minimal_k(a, 0.9) in (1, 3, 12)


def test_convergence_surfaces_unstable_single_run_ranking():
    runs = []
    for i in range(20):
        # x wins the pooled median (11 of 20 runs) but loses 9 single runs
        if i < 11:
            runs.append({"x": 2000, "y": 1000})
        else:
            runs.append({"x": 1000, "y": 2000})
    rows = stats.convergence(runs, [1, 3, 20], draws=400, seed=3)
    assert 0.4 < rows[0]["top1_agreement"] < 0.7
    assert set(rows[0]["single_run_top1"]) == {"x", "y"}
    assert rows[-1]["top1_agreement"] == 1.0
