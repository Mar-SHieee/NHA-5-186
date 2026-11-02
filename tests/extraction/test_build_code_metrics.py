import importlib.util
import json
import sys

import pandas as pd
import pytest

from shield_core import paths
from shield_core.extraction.ts_utils import FEATURE_NAMES, compute_metrics

# The script lives in scripts/, which is not a package, so load it by its file path.
_SCRIPT = paths.REPO_ROOT / "scripts" / "training" / "build_code_metrics.py"
_spec = importlib.util.spec_from_file_location("build_code_metrics", _SCRIPT)
bcm = importlib.util.module_from_spec(_spec)
sys.modules["build_code_metrics"] = bcm
_spec.loader.exec_module(bcm)

PY = "def f(a):\n    if a:\n        return 1\n    return 0\n"
PY_FIXED = PY.replace("return 0", "return 2")
PY2 = "def g(a):\n    for i in a:\n        pass\n"
C1 = "int h(int a){ if (a && a > 1) { return 1; } return 0; }"
C2 = C1.replace("a > 1", "a > 2")
BAD = "def bad(:\n    pass\n"
_COLUMNS = ["code", "language", "label", "source", "fixed_code"]


def _write(directory, name, rows):
    pd.DataFrame(rows, columns=_COLUMNS).to_parquet(directory / f"{name}.parquet", index=False)


@pytest.fixture
def workdir(tmp_path):
    splits = tmp_path / "splits"
    splits.mkdir()
    _write(
        splits,
        "train",
        [
            (PY, "python", 1, "cvefixes_python", PY_FIXED),
            (C1, "cpp", 0, "megavul", None),
            (BAD, "python", 0, "cvefixes_python", None),
        ],
    )
    _write(
        splits,
        "val",
        [
            (PY2, "python", 0, "cvefixes_python", None),
            (C1, "cpp", 0, "megavul", None),  # same text as a train row
            ("   ", "cpp", 0, "megavul", None),  # blank
            ("class A {}", "java", 0, "megavul", None),  # language that is not enabled
        ],
    )
    _write(splits, "test", [(C2, "cpp", 1, "megavul", C1)])
    _write(splits, "holdout", [(PY, "python", 0, "cvefixes_python", None)])
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"manifest_version": "t1", "dataset_hash": "abc"}))
    return {
        "splits_dir": splits,
        "manifest_path": manifest,
        "out_dir": tmp_path / "out",
        "report_path": tmp_path / "report.md",
    }


def _build(work, **kwargs):
    kwargs.setdefault("log", lambda message: None)
    return bcm.build(
        work["splits_dir"], work["manifest_path"], work["out_dir"], work["report_path"], **kwargs
    )


def _load(work, **kwargs):
    return bcm.load_code_metrics(
        work["out_dir"], work["manifest_path"], work["splits_dir"], **kwargs
    )


# ---------------------------------------------------------------- what is measured


def test_every_distinct_function_is_measured_once_fixed_code_included(workdir):
    _build(workdir)
    table = _load(workdir)
    expected = {("python", PY), ("python", PY_FIXED), ("python", PY2), ("python", BAD)}
    expected |= {("cpp", C1), ("cpp", C2)}
    assert set(zip(table["language"], table["code_sha256"], strict=True)) == {
        (language, bcm.code_sha256(code)) for language, code in expected
    }
    assert not table.duplicated(bcm.KEY).any()


def test_the_numbers_are_the_ones_compute_metrics_gives(workdir):
    _build(workdir)
    table = _load(workdir)
    by_key = {(r.language, r.code_sha256): r for r in table.itertuples()}
    for language, code in [("python", PY), ("cpp", C1), ("python", BAD)]:
        row = by_key[(language, bcm.code_sha256(code))]
        expected = compute_metrics(code, language)
        assert [getattr(row, name) for name in FEATURE_NAMES] == [
            getattr(expected, name) for name in FEATURE_NAMES
        ]


def test_columns_and_dtypes(workdir):
    _build(workdir)
    table = _load(workdir)
    assert list(table.columns) == ["language", "code_sha256", *FEATURE_NAMES]
    assert table["cyclomatic"].dtype == "int32"
    assert table["has_parse_error"].dtype == "bool"


def test_a_broken_function_stays_in_the_table_with_its_flag(workdir):
    _build(workdir)
    table = _load(workdir)
    flag = table.set_index("code_sha256").loc[bcm.code_sha256(BAD), "has_parse_error"]
    assert bool(flag) is True


def test_blank_code_and_disabled_languages_are_skipped_and_counted(workdir):
    meta = _build(workdir)
    assert meta["skipped"] == {"empty_code": 1, "language:java": 1}


def test_the_same_text_in_two_languages_is_measured_for_each(workdir):
    same = "for i in a:\n    pass\n"  # a loop in Python, a syntax error in C++
    python_numbers = compute_metrics(same, "python")
    cpp_numbers = compute_metrics(same, "cpp")
    assert python_numbers != cpp_numbers  # otherwise this test proves nothing
    _write(
        workdir["splits_dir"],
        "holdout",
        [(same, "python", 0, "cvefixes_python", None), (same, "cpp", 0, "megavul", None)],
    )
    _build(workdir)
    table = _load(workdir)
    rows = table[table["code_sha256"] == bcm.code_sha256(same)]
    assert sorted(rows["language"]) == ["cpp", "python"]
    frame = pd.DataFrame({"code": [same, same], "language": ["python", "cpp"], "label": [0, 0]})
    out = bcm.attach_code_metrics(frame, table)
    assert list(out["n_loops"]) == [python_numbers.n_loops, cpp_numbers.n_loops]
    assert list(out["has_parse_error"]) == [False, True]


def test_batch_size_does_not_change_the_table(workdir):
    _build(workdir, batch_size=1)
    small = _load(workdir).sort_values(bcm.KEY).reset_index(drop=True)
    _build(workdir, batch_size=1000)
    big = _load(workdir).sort_values(bcm.KEY).reset_index(drop=True)
    pd.testing.assert_frame_equal(small, big)


def test_progress_is_logged_per_batch(workdir):
    lines = []
    _build(workdir, batch_size=2, log=lines.append)
    assert any("functions/s" in line for line in lines)
    assert any(line.startswith("[train]") for line in lines)


def test_invalid_characters_do_not_crash_and_do_not_change_the_key():
    assert bcm.code_sha256("a\ud800b") == bcm.code_sha256("ab")
    assert bcm._clean("a\ud800b") == "ab"


# ---------------------------------------------------------------- the files that come out


def test_meta_records_what_the_table_came_from(workdir):
    _build(workdir)
    meta = json.loads((workdir["out_dir"] / bcm.META_NAME).read_text())
    assert meta["manifest_dataset_hash"] == "abc"
    assert meta["split_rows"] == {"train": 3, "val": 4, "test": 1, "holdout": 1}
    assert meta["feature_names"] == list(FEATURE_NAMES)
    assert meta["distinct_functions"] == 6
    assert "ts_utils.py" in meta["code_hashes"]


def test_report_has_its_sections_and_the_parse_error_rate(workdir):
    _build(workdir)
    text = workdir["report_path"].read_text()
    for heading in ("## 1. Inputs", "## 2. Rows and parse errors", "## 4. Do the numbers"):
        assert heading in text
    assert "| python | cvefixes_python |" in text


def test_a_trial_run_is_marked_partial_and_refused(workdir):
    meta = _build(workdir, limit=2)
    assert meta["distinct_functions"] == 2
    assert "PARTIAL RUN" in workdir["report_path"].read_text()
    with pytest.raises(bcm.StaleCodeMetricsError, match="partial"):
        _load(workdir)
    assert len(_load(workdir, check=False)) == 2


def test_main_runs_from_the_command_line(workdir):
    argv = [
        "--splits-dir",
        str(workdir["splits_dir"]),
        "--manifest",
        str(workdir["manifest_path"]),
        "--out-dir",
        str(workdir["out_dir"]),
        "--report",
        str(workdir["report_path"]),
    ]
    assert bcm.main(argv) == 0
    assert len(_load(workdir)) == 6


def test_missing_split_file_is_named(workdir):
    (workdir["splits_dir"] / "test.parquet").unlink()
    with pytest.raises(FileNotFoundError, match="test.parquet"):
        _build(workdir)


def test_missing_manifest_is_named(workdir):
    workdir["manifest_path"].unlink()
    with pytest.raises(FileNotFoundError, match="manifest"):
        _build(workdir)


# ---------------------------------------------------------------- is the table still current?


def test_a_fresh_table_passes_the_check(workdir):
    _build(workdir)
    assert len(_load(workdir)) == 6


def test_a_new_manifest_hash_makes_the_table_stale(workdir):
    _build(workdir)
    workdir["manifest_path"].write_text(json.dumps({"manifest_version": "t2", "dataset_hash": "x"}))
    with pytest.raises(bcm.StaleCodeMetricsError, match="manifest hash"):
        _load(workdir)


def test_a_split_with_other_row_count_makes_the_table_stale(workdir):
    _build(workdir)
    _write(
        workdir["splits_dir"], "test", [(C2, "cpp", 1, "megavul", C1), (C1, "cpp", 0, "x", None)]
    )
    with pytest.raises(bcm.StaleCodeMetricsError, match="rows in a split"):
        _load(workdir)


def test_changed_metric_code_makes_the_table_stale(workdir, monkeypatch):
    _build(workdir)
    monkeypatch.setattr(bcm, "_fingerprint_files", lambda: {"ts_utils.py": "other"})
    with pytest.raises(bcm.StaleCodeMetricsError, match="ts_utils.py or a language yaml"):
        _load(workdir)


def test_missing_table_asks_to_run_the_script(workdir):
    with pytest.raises(FileNotFoundError, match="build_code_metrics.py"):
        _load(workdir)


# ---------------------------------------------------------------- joining it to a dataframe


def _p3_style_frame():
    """Rows in a different order, a repeated index, and fixed code as a label-0 row."""
    frame = pd.DataFrame(
        {
            "code": [C1, PY_FIXED, PY, BAD],
            "language": ["cpp", "python", "python", "python"],
            "label": [0, 0, 1, 0],
        },
        index=[7, 3, 9, 1],
    )
    return frame


def test_attach_matches_by_code_and_keeps_order_and_index(workdir):
    _build(workdir)
    frame = _p3_style_frame()
    out = bcm.attach_code_metrics(frame, _load(workdir))
    assert list(out.index) == [7, 3, 9, 1]
    assert list(out["label"]) == [0, 0, 1, 0]
    for label, row in out.iterrows():
        expected = compute_metrics(frame.loc[label, "code"], frame.loc[label, "language"])
        assert [row[name] for name in FEATURE_NAMES] == [
            getattr(expected, name) for name in FEATURE_NAMES
        ]


def test_attach_keeps_the_compact_dtypes(workdir):
    _build(workdir)
    out = bcm.attach_code_metrics(_p3_style_frame(), _load(workdir))
    assert out["n_lines"].dtype == "int32"
    assert out["has_parse_error"].dtype == "bool"


def test_attach_refuses_code_that_is_not_in_the_table(workdir):
    _build(workdir)
    frame = _p3_style_frame()
    frame.loc[7, "code"] = "int unseen(void){ return 1; }"
    with pytest.raises(ValueError, match="1 rows have code that is not in the metric table"):
        bcm.attach_code_metrics(frame, _load(workdir))


def test_attach_does_not_change_its_input(workdir):
    _build(workdir)
    frame = _p3_style_frame()
    before = frame.copy()
    bcm.attach_code_metrics(frame, _load(workdir))
    pd.testing.assert_frame_equal(frame, before)
