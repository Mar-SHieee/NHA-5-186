"""CI test for split QA - W2-P5-04 required checks."""

import json

import pandas as pd

from scripts.split_qa import Check, QAResult, _normalize_cve, run_qa


def _make_manifest(tmp_path, splits: dict):
    manifest = {
        "manifest_version": "v0.2",
        "seed": 42,
        "dataset_hash": "testhash",
        "target_ratios": {s: 0.25 for s in splits},
        "splits": {s: {"rows": len(df)} for s, df in splits.items()},
        "files": {},
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    splits_dir = tmp_path / "splits"
    splits_dir.mkdir()
    for s, df in splits.items():
        df.to_parquet(splits_dir / f"{s}.parquet", index=False)
    return manifest_path, splits_dir


def _base_rows(n=10, project="a/b", commit="abc", cve="CVE-2023-0001", code="code"):
    return pd.DataFrame(
        {
            "code": [f"{code}{i}" for i in range(n)],
            "label": [1] * n,
            "cwe": [["CWE-79"]] * n,
            "project": [project] * n,
            "commit": [commit] * n,
            "cve": [[cve]] * n,
            "source": ["test"] * n,
        }
    )


def test_normalize_cve():
    assert _normalize_cve("cve-2023-1234") == "CVE-2023-1234"
    assert _normalize_cve("  CVE-2023-1234  ") == "CVE-2023-1234"
    assert _normalize_cve("CVE-2023-1234, extra") == "CVE-2023-1234"
    assert _normalize_cve("") is None
    assert _normalize_cve(None) is None


def test_qa_passes_when_clean(tmp_path):
    splits = {
        "train": _base_rows(10, "proj/a", "commit1", "CVE-2023-0001", "codeA"),
        "val": _base_rows(10, "proj/b", "commit2", "CVE-2023-0002", "codeB"),
        "test": _base_rows(10, "proj/c", "commit3", "CVE-2023-0003", "codeC"),
        "holdout": _base_rows(10, "proj/d", "commit4", "CVE-2023-0004", "codeD"),
    }
    manifest_path, splits_dir = _make_manifest(tmp_path, splits)
    result = run_qa(manifest_path, splits_dir, mapping_dir=None)
    assert result.failures == [], f"Should pass but got {result.failures}"
    assert result.split_table["rows"].sum() == 40


def test_qa_fails_on_project_commit_group_leak(tmp_path):
    df1 = _base_rows(5, "proj/a", "same_commit", "CVE-2023-0001", "codeA")
    df2 = _base_rows(5, "proj/a", "same_commit", "CVE-2023-0001", "codeB")
    splits = {
        "train": df1,
        "val": df2,
        "test": _base_rows(5, "proj/c", "c3", "CVE-2023-0003", "codeC"),
        "holdout": _base_rows(5, "proj/d", "c4", "CVE-2023-0004", "codeD"),
    }
    manifest_path, splits_dir = _make_manifest(tmp_path, splits)
    result = run_qa(manifest_path, splits_dir, None)
    names = [c.name for c in result.failures]
    assert "(project, commit) group crossing" in names
    assert "commit crossing" in names


def test_qa_fails_on_cve_component_crossing(tmp_path):
    df1 = _base_rows(5, "proj/a", "commit1", "CVE-2023-9999", "codeA")
    df2 = _base_rows(5, "proj/b", "commit2", "CVE-2023-9999", "codeB")
    splits = {
        "train": df1,
        "val": df2,
        "test": _base_rows(5, "proj/c", "c3", "CVE-2023-0003", "codeC"),
        "holdout": _base_rows(5, "proj/d", "c4", "CVE-2023-0004", "codeD"),
    }
    manifest_path, splits_dir = _make_manifest(tmp_path, splits)
    result = run_qa(manifest_path, splits_dir, None)
    names = [c.name for c in result.failures]
    assert "CVE component crossing" in names


def test_qa_fails_on_row_count_mismatch(tmp_path):
    df_train = _base_rows(10, "proj/a", "c1", "CVE-1", "codeA")
    df_val = _base_rows(10, "proj/b", "c2", "CVE-2", "codeB")
    splits = {
        "train": df_train,
        "val": df_val,
        "test": df_train,
        "holdout": df_train,
    }
    manifest_path, splits_dir = _make_manifest(tmp_path, splits)
    manifest = json.loads(manifest_path.read_text())
    manifest["splits"]["train"]["rows"] = 999
    manifest_path.write_text(json.dumps(manifest))
    result = run_qa(manifest_path, splits_dir, None)
    assert any(c.name == "manifest row counts" for c in result.failures)


def test_qa_fails_on_exact_code_overlap(tmp_path):
    df1 = _base_rows(5, "proj/a", "c1", "CVE-1", "SAME_CODE")
    df2 = _base_rows(5, "proj/b", "c2", "CVE-2", "SAME_CODE")
    splits = {
        "train": df1,
        "val": df2,
        "test": _base_rows(5, "proj/c", "c3", "CVE-3", "codeC"),
        "holdout": _base_rows(5, "proj/d", "c4", "CVE-4", "codeD"),
    }
    manifest_path, splits_dir = _make_manifest(tmp_path, splits)
    result = run_qa(manifest_path, splits_dir, None)
    assert any(c.name == "exact code-hash overlap" for c in result.failures)


def test_exit_code_logic():
    manifest = {"manifest_version": "v0.2", "seed": 42, "dataset_hash": "abc"}
    clean_result = QAResult(manifest=manifest, checks=[Check("test", "desc", 0)])
    assert clean_result.failures == []

    fail_result = QAResult(manifest=manifest, checks=[Check("test", "desc", 1)])
    assert len(fail_result.failures) == 1
