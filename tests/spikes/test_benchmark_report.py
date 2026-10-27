from scripts.spikes.joern.benchmark_report import (
    _recommendation,
    aggregate_results,
    projection_rows,
    render_report,
    replace_section,
    scale_spike_comparisons,
    scale_tail_statistics,
    scenario_counts,
)


def _row(variant, rep, wall, **extra):
    row = {
        "experiment": "E4",
        "variant": variant,
        "group": "python",
        "set_name": "spike",
        "workers": "1",
        "batch_size": "1",
        "xmx": "4g",
        "rep": str(rep),
        "wall_seconds": str(wall),
        "n_samples": "10",
        "ok_count": "10",
        "fail_count": "0",
        "peak_mib": "100",
    }
    row.update(extra)
    return row


def test_aggregate_uses_median_and_ignores_warmup():
    rows = aggregate_results(
        [
            _row("A", 0, 1, experiment="E3"),
            _row("A", 1, 4, experiment="E3"),
            _row("A", 2, 6, experiment="E3"),
            _row("B", 1, 2, experiment="E3"),
        ]
    )
    a = next(row for row in rows if row["variant"] == "A")
    assert a["median_wall_seconds"] == 5
    assert a["min_wall_seconds"] == 4
    assert a["max_wall_seconds"] == 6
    assert a["success_rate"] == 1
    b = next(row for row in rows if row["variant"] == "B")
    assert b["speedup"] == 2.5
    assert b["efficiency"] is None


def test_worker_speedup_uses_same_variant_one_worker_baseline():
    rows = aggregate_results(
        [
            _row("A", 1, 5, experiment="E4", workers="1"),
            _row("A", 1, 2.5, experiment="E4", workers="2"),
        ]
    )
    two_workers = next(row for row in rows if row["workers"] == "2")
    assert two_workers["speedup"] == 2
    assert two_workers["efficiency"] == 1


def test_empty_floor_has_no_success_rate():
    row = aggregate_results(
        [
            _row(
                "floor",
                1,
                0.8,
                experiment="E2",
                ok_count="0",
                fail_count="0",
                n_samples="0",
            )
        ]
    )[0]
    assert row["success_rate"] is None


def test_projection_arithmetic():
    projected = projection_rows(
        {"A": {"throughput": 2.0, "p95_seconds_per_sample": 1.0}},
        {"S1": {"python": 7200}},
    )
    assert projected[0]["hours_median"] == 1
    assert projected[0]["hours_pessimistic"] == 2
    assert projected[0]["rows_per_night"] == 72000


def test_marker_replacement_is_idempotent_and_preserves_outside_text():
    original = "before\n<!-- BENCHMARK:BEGIN -->\nold\n<!-- BENCHMARK:END -->\nafter\n"
    once = replace_section(original, "## New")
    assert replace_section(once, "## New") == once
    assert once.startswith("before\n")
    assert once.endswith("\nafter\n")
    assert "old" not in once


def test_missing_experiments_render_as_not_run():
    report = render_report([], [], {}, {})
    assert "not run" in report


def test_scenario_counts_read_totals_and_filter_in_scope_cwes(tmp_path):
    import pandas as pd

    tables = {
        "cvefixes_python_deduped.parquet": ([1, 1, 0], [["CWE-22"], ["CWE-502"], []]),
        "bigvul_deduped.parquet": ([1, 0], [["CWE-120"], []]),
        "cvefixes_cpp_deduped.parquet": ([1], [["CWE-835"]]),
        "megavul_deduped.parquet": ([1, 0], [["CWE-122"], []]),
    }
    for filename, (labels, cwes) in tables.items():
        pd.DataFrame({"label": labels, "cwe": cwes}).to_parquet(tmp_path / filename)

    counts, source = scenario_counts(tmp_path)
    assert source.startswith("parquet counts")
    assert counts["python"] == {"S1": 3, "S2": 1, "S3": 2, "S4": 4, "S5": 3}
    assert counts["c"] == {"S1": 3, "S2": 1, "S3": 2, "S4": 4, "S5": 0}
    assert counts["cpp"]["S2"] == 1


def test_scenario_counts_label_missing_parquet_as_fallback(tmp_path):
    counts, source = scenario_counts(tmp_path)
    assert counts == {}
    assert "fallback" in source


def test_scale_tail_statistics_reports_tail_failures_and_correlation():
    results = [
        {
            "run_id": "scale-1",
            "experiment": "E5",
            "rep": "1",
            "variant": "C",
            "group": "python",
            "workers": "4",
            "batch_size": "20",
        }
    ]
    samples = [
        {
            "run_id": "scale-1",
            "sample_id": "a",
            "ok": "1",
            "seconds": "1",
            "n_lines": "10",
            "failure_class": "",
        },
        {
            "run_id": "scale-1",
            "sample_id": "b",
            "ok": "1",
            "seconds": "2",
            "n_lines": "20",
            "failure_class": "",
        },
        {
            "run_id": "scale-1",
            "sample_id": "c",
            "ok": "1",
            "seconds": "3",
            "n_lines": "30",
            "failure_class": "",
        },
        {
            "run_id": "scale-1",
            "sample_id": "d",
            "ok": "0",
            "seconds": "0",
            "n_lines": "40",
            "failure_class": "timeout",
        },
    ]
    row = scale_tail_statistics(results, samples)[0]
    assert row["p50_seconds"] == 2
    assert row["p95_seconds"] == 3
    assert row["max_seconds"] == 3
    assert row["timeouts"] == 1
    assert row["timeout_ids"] == "d"
    assert row["slowest_5pct_share"] == 0.5
    assert row["lines_seconds_correlation"] == 1


def test_scale_spike_comparison_flags_changes_over_25_percent():
    base = {
        "variant": "C",
        "group": "python",
        "workers": "4",
        "batch_size": "20",
        "success_rate": 1.0,
        "experiment": "E4",
        "throughput": 1.0,
    }
    scale = {**base, "experiment": "E5", "throughput": 1.3}
    comparison = scale_spike_comparisons([base, scale])[0]
    assert abs(comparison["change"] - 0.3) < 1e-9
    assert comparison["over_25pct"] is True


def test_failed_batch_fidelity_uses_fastest_non_batched_recommendation():
    rows = [
        {
            "experiment": "E3",
            "group": "python",
            "variant": "A",
            "batch_size": "1",
            "workers": "1",
            "throughput": 0.2,
            "success_rate": 1.0,
            "median_wall_seconds": 5.0,
        },
        {
            "experiment": "E3",
            "group": "python",
            "variant": "B",
            "batch_size": "1",
            "workers": "1",
            "throughput": 0.25,
            "success_rate": 1.0,
            "median_wall_seconds": 4.0,
        },
        {
            "experiment": "E5",
            "group": "python",
            "variant": "C",
            "batch_size": "20",
            "workers": "4",
            "throughput": 2.0,
            "success_rate": 1.0,
            "median_wall_seconds": 1.0,
        },
    ]
    fidelity = {"groups": {"python": {"verdict": "not usable"}}}
    result = _recommendation(rows, fidelity)
    assert "python: B (non-batched" in result
    assert "python: C" not in result
