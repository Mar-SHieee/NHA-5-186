"""Tests for scripts/spikes/joern/benchmark_core.py (W2-P2-05). No Docker needed."""

import pytest

from scripts.spikes.joern.benchmark_core import (
    RESULT_COLUMNS,
    SAMPLE_COLUMNS,
    append_row,
    classify_failure,
    completed_keys,
    config_key,
    parse_markers,
    project_hours,
    read_rows,
    rows_per_night,
    split_batches,
    summarize,
)

# ----------------------------------------------------------------------------- split_batches


def test_split_batches_exact_division():
    assert split_batches([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


def test_split_batches_keeps_remainder_in_last_batch():
    assert split_batches([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_split_batches_size_larger_than_list():
    assert split_batches([1, 2, 3], 10) == [[1, 2, 3]]


def test_split_batches_empty_list():
    assert split_batches([], 3) == []


@pytest.mark.parametrize("bad", [0, -1])
def test_split_batches_rejects_non_positive_size(bad):
    with pytest.raises(ValueError):
        split_batches([1, 2], bad)


# ----------------------------------------------------------------------------- summarize


def test_summarize_odd_length_median_is_the_middle_value():
    s = summarize([3.0, 1.0, 2.0])
    assert s["n"] == 3
    assert s["median"] == 2.0
    assert s["min"] == 1.0 and s["max"] == 3.0
    assert s["mean"] == pytest.approx(2.0)


def test_summarize_even_length_median_averages_the_middle_two():
    assert summarize([1.0, 2.0, 3.0, 4.0])["median"] == 2.5


def test_summarize_p95_is_nearest_rank():
    # nearest-rank: rank = ceil(0.95 * n), 1-indexed. n = 20 -> rank 19 -> value 19.
    assert summarize([float(i) for i in range(1, 21)])["p95"] == 19.0


def test_summarize_single_value():
    s = summarize([7.5])
    assert s["median"] == s["p95"] == s["min"] == s["max"] == 7.5


def test_summarize_empty_returns_n_zero_and_nones():
    s = summarize([])
    assert s["n"] == 0
    assert s["mean"] is None and s["median"] is None and s["p95"] is None


# ----------------------------------------------------------------------------- projections


def test_project_hours_reproduces_the_old_740_hour_figure():
    # 5.85 s per sample, one worker, 455,236 rows (SHIELD_PLAN D38)
    assert project_hours(455_236, 1 / 5.85) == pytest.approx(739.8, abs=0.1)


def test_project_hours_scales_with_throughput():
    assert project_hours(3600, 1.0) == pytest.approx(1.0)
    assert project_hours(3600, 2.0) == pytest.approx(0.5)


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_project_hours_rejects_non_positive_throughput(bad):
    with pytest.raises(ValueError):
        project_hours(100, bad)


def test_rows_per_night_default_is_ten_hours():
    assert rows_per_night(1.0) == 36_000


def test_rows_per_night_custom_hours():
    assert rows_per_night(0.5, hours=2.0) == 3_600


# ----------------------------------------------------------------------------- parse_markers

SAMPLE_OUTPUT = """\
Parsing code at: /workspace/job/a.py - language: `PYTHONSRC`
[+] Running language frontend
@@T parse_0 3.412
@@T export_0 1.208
Successfully wrote graph to: /tmp/cpg.bin
@@FAIL sample_17 1
@@PEAK 187695104
"""


def test_parse_markers_reads_timings_failures_and_peak():
    m = parse_markers(SAMPLE_OUTPUT)
    assert m.timings == {"parse_0": 3.412, "export_0": 1.208}
    assert m.failures == {"sample_17": 1}
    assert m.peak_bytes == 187_695_104


def test_parse_markers_ignores_noise_lines():
    m = parse_markers("hello\n[+] Running\n@@T a 1.5\nrandom @@T not-at-line-start 9\n")
    assert m.timings == {"a": 1.5}


def test_parse_markers_peak_na_means_unknown():
    assert parse_markers("@@PEAK NA\n").peak_bytes is None


def test_parse_markers_without_any_marker():
    m = parse_markers("nothing useful here\n")
    assert m.timings == {} and m.failures == {} and m.peak_bytes is None


def test_parse_markers_skips_malformed_marker_lines():
    m = parse_markers("@@T onlyname\n@@T x notanumber\n@@PEAK abc\n@@T good 2.0\n")
    assert m.timings == {"good": 2.0}
    assert m.peak_bytes is None


def test_parse_markers_handles_windows_line_endings():
    assert parse_markers("@@T a 1.0\r\n@@PEAK 10\r\n").peak_bytes == 10


# ----------------------------------------------------------------------------- classify_failure


def test_classify_ok():
    assert classify_failure(0, False, "", True) == "ok"


def test_classify_timeout_wins_over_everything():
    assert classify_failure(None, True, "Cannot connect to the Docker daemon", False) == "timeout"


def test_classify_oom_by_exit_code_137():
    assert classify_failure(137, False, "", False) == "oom"


def test_classify_oom_by_java_message():
    err = "Exception in thread main java.lang.OutOfMemoryError: Java heap space"
    assert classify_failure(1, False, err, False) == "oom"


def test_classify_docker_daemon_unreachable():
    err = "docker: Cannot connect to the Docker daemon at npipe:////./pipe/docker_engine"
    assert classify_failure(1, False, err, False) == "docker_error"


def test_classify_docker_run_failure_exit_code_125():
    assert classify_failure(125, False, "", False) == "docker_error"


def test_classify_joern_error_on_other_non_zero_exit():
    assert classify_failure(1, False, "some joern stack trace", False) == "joern_error"


def test_classify_no_export_when_exit_zero_but_file_missing():
    assert classify_failure(0, False, "", False) == "no_export"


def test_classify_unknown_exit_without_timeout_is_docker_error():
    assert classify_failure(None, False, "", False) == "docker_error"


def test_failure_classes_constant_lists_every_label():
    from scripts.spikes.joern.benchmark_core import FAILURE_CLASSES

    assert set(FAILURE_CLASSES) == {
        "ok",
        "timeout",
        "oom",
        "joern_error",
        "no_export",
        "xml_error",
        "docker_error",
    }


def test_parse_markers_rejects_non_finite_timings():
    m = parse_markers("@@T a nan\n@@T b inf\n@@T c 1.0\n")
    assert m.timings == {"c": 1.0}


# ----------------------------------------------------------------------------- column lists


def test_result_columns_match_the_plan_exactly():
    assert RESULT_COLUMNS == [
        "run_id",
        "timestamp_utc",
        "experiment",
        "variant",
        "group",
        "extension",
        "set_name",
        "n_samples",
        "batch_size",
        "workers",
        "xmx",
        "rep",
        "wall_seconds",
        "seconds_per_sample",
        "samples_per_second",
        "ok_count",
        "fail_count",
        "fail_reasons_json",
        "peak_mib",
        "peak_method",
        "parse_seconds",
        "export_seconds",
        "xml_parse_seconds",
        "notes",
    ]


def test_sample_columns_match_the_plan_exactly():
    assert SAMPLE_COLUMNS == [
        "run_id",
        "sample_id",
        "group",
        "n_chars",
        "n_lines",
        "seconds",
        "ok",
        "failure_class",
        "nodes",
        "edges",
    ]


def test_column_lists_have_no_duplicates():
    assert len(set(RESULT_COLUMNS)) == len(RESULT_COLUMNS)
    assert len(set(SAMPLE_COLUMNS)) == len(SAMPLE_COLUMNS)


# ----------------------------------------------------------------------------- config_key


def test_config_key_turns_every_part_into_a_string():
    assert config_key("A", "python", "spike", 1, 1, "4g", 2) == (
        "A",
        "python",
        "spike",
        "1",
        "1",
        "4g",
        "2",
    )


def test_config_key_is_equal_for_int_and_string_parts():
    assert config_key("B", "c", "scale", 4, 20, "2g", 1) == config_key(
        "B", "c", "scale", "4", "20", "2g", "1"
    )


# ----------------------------------------------------------------------------- append / read

COLS = ["a", "b", "c"]


def test_append_row_creates_file_with_header_once(tmp_path):
    path = tmp_path / "sub" / "r.csv"  # the parent folder does not exist yet
    append_row(path, COLS, {"a": 1, "b": "x", "c": 2.5})
    append_row(path, COLS, {"a": 2, "b": "y", "c": 3.5})
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "a,b,c"
    assert len(lines) == 3


def test_read_rows_roundtrip_returns_strings_in_order(tmp_path):
    path = tmp_path / "r.csv"
    append_row(path, COLS, {"a": 1, "b": "x", "c": 2.5})
    append_row(path, COLS, {"a": 2, "b": "y", "c": 3.5})
    assert read_rows(path) == [
        {"a": "1", "b": "x", "c": "2.5"},
        {"a": "2", "b": "y", "c": "3.5"},
    ]


def test_read_rows_missing_file_is_an_empty_list(tmp_path):
    assert read_rows(tmp_path / "does_not_exist.csv") == []


def test_append_row_writes_none_and_missing_values_as_empty_cells(tmp_path):
    path = tmp_path / "r.csv"
    append_row(path, COLS, {"a": 1, "b": None})  # "c" missing, "b" is None
    assert read_rows(path) == [{"a": "1", "b": "", "c": ""}]


def test_append_row_rejects_unknown_column(tmp_path):
    with pytest.raises(ValueError):
        append_row(tmp_path / "r.csv", COLS, {"a": 1, "zzz": 2})


def test_append_row_rejects_a_file_with_a_different_header(tmp_path):
    path = tmp_path / "r.csv"
    append_row(path, COLS, {"a": 1})
    with pytest.raises(ValueError):
        append_row(path, ["a", "b", "other"], {"a": 2})


def test_append_row_quotes_commas_quotes_and_newlines(tmp_path):
    path = tmp_path / "r.csv"
    tricky = '{"timeout": 2, "oom": 1}'
    append_row(path, COLS, {"a": tricky, "b": 'say "hi", please', "c": "line1\nline2"})
    row = read_rows(path)[0]
    assert row == {"a": tricky, "b": 'say "hi", please', "c": "line1\nline2"}


def test_append_row_accepts_a_str_path(tmp_path):
    append_row(str(tmp_path / "r.csv"), COLS, {"a": 1})
    assert len(read_rows(str(tmp_path / "r.csv"))) == 1


# ----------------------------------------------------------------------------- completed_keys


def _result_row(rep, variant="A", group="python", **extra):
    row = {
        "variant": variant,
        "group": group,
        "set_name": "spike",
        "workers": 1,
        "batch_size": 1,
        "xmx": "4g",
        "rep": rep,
    }
    row.update(extra)
    return row


def test_completed_keys_matches_config_key_after_a_csv_roundtrip(tmp_path):
    path = tmp_path / "results.csv"
    append_row(path, RESULT_COLUMNS, _result_row(rep=1))
    keys = completed_keys(read_rows(path))
    assert config_key("A", "python", "spike", 1, 1, "4g", 1) in keys


def test_completed_keys_ignores_warm_up_runs(tmp_path):
    path = tmp_path / "results.csv"
    append_row(path, RESULT_COLUMNS, _result_row(rep=0))
    assert completed_keys(read_rows(path)) == set()


def test_completed_keys_counts_failed_runs_as_completed(tmp_path):
    path = tmp_path / "results.csv"
    append_row(path, RESULT_COLUMNS, _result_row(rep=1, ok_count=0, fail_count=20))
    assert len(completed_keys(read_rows(path))) == 1


def test_completed_keys_distinguishes_configurations(tmp_path):
    path = tmp_path / "results.csv"
    append_row(path, RESULT_COLUMNS, _result_row(rep=1, variant="A"))
    append_row(path, RESULT_COLUMNS, _result_row(rep=1, variant="B"))
    append_row(path, RESULT_COLUMNS, _result_row(rep=2, variant="A"))
    assert len(completed_keys(read_rows(path))) == 3


def test_completed_keys_of_nothing_is_empty():
    assert completed_keys([]) == set()
