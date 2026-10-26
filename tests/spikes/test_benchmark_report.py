from scripts.spikes.joern.benchmark_report import (
    aggregate_results,
    projection_rows,
    render_report,
    replace_section,
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
    rows = aggregate_results([_row("A", 0, 1), _row("A", 1, 4), _row("A", 2, 6), _row("B", 1, 2)])
    a = next(row for row in rows if row["variant"] == "A")
    assert a["median_wall_seconds"] == 5
    assert a["min_wall_seconds"] == 4
    assert a["max_wall_seconds"] == 6
    assert a["success_rate"] == 1
    b = next(row for row in rows if row["variant"] == "B")
    assert b["speedup"] == 2.5
    assert b["efficiency"] == 2.5


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
