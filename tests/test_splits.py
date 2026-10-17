"""Tests for project-disjoint, CWE-balanced splitting (W2-P1-01)."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from shield_core.datasets import schema, splits

COMMON = ["CWE-79", "CWE-89", "CWE-22", "CWE-787"]


def _frame(rows: list[dict]) -> pd.DataFrame:
    base = {
        "code": "x",
        "language": "python",
        "label": 1,
        "cwe": [],
        "project": pd.NA,
        "commit": pd.NA,
        "date": pd.NA,
        "cve": [],
        "fixed_code": pd.NA,
        "source": "t",
    }
    out = pd.DataFrame([{**base, **r, "code": f"code{i}"} for i, r in enumerate(rows)])
    return out[schema.COLUMNS].astype(schema.DTYPES)


def synthetic(n_projects: int = 400, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for p in range(n_projects):
        cwe = "CWE-999" if p < 2 else COMMON[rng.choice(4, p=[0.4, 0.3, 0.2, 0.1])]
        for k in range(int(rng.integers(1, 4))):
            commit = "deadbeef" if p in (5, 6) else f"{p}-{k}"
            for _ in range(int(rng.integers(1, 6))):
                vuln = rng.random() < 0.8
                rows.append(
                    {
                        "project": f"proj_{p}",
                        "commit": commit,
                        "label": int(vuln),
                        "cwe": [cwe] if vuln else [],
                    }
                )
    return _frame(rows)


# ------------------------------------------------------------------ normalizer
def test_canonical_project_uses_normalize_project_name():
    assert splits.NORMALIZER_NAME.endswith("project_normalization.normalize_project_name")
    assert splits.canonical_project("linux") == "torvalds/linux"  # verified alias
    assert splits.canonical_project("  PHP ") == "php/php-src"  # case/whitespace + alias
    assert splits.canonical_project("some/other") == "some/other"  # unknown names untouched


@pytest.mark.parametrize("value", [None, pd.NA, float("nan"), "", "  ", "unknown", "NaN", "None"])
def test_missing_project_values_are_none(value):
    assert splits.canonical_project(value) is None


def test_verified_aliases_are_one_project():
    rows = [
        {"project": "linux", "commit": "a1"},
        {"project": "Linux ", "commit": "b2"},
        {"project": "torvalds/linux", "commit": "c3"},
    ]
    rows += [{"project": f"p{i}", "commit": f"c{i}"} for i in range(40)]
    a = splits.make_assignments(_frame(rows))
    assert (a.loc[:2, "project_key"] == "torvalds/linux").all()
    assert a.loc[:2, "split"].nunique() == 1


# ------------------------------------------------------------------ leakage
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_no_project_commit_or_group_leakage(seed):
    df = synthetic(seed=seed)
    extra = _frame(
        [  # alias spellings, commit shared across projects, commit-only and project-only rows
            {"project": "linux", "commit": "x1"},
            {"project": "torvalds/linux", "commit": "x2"},
            {"project": "ffmpeg", "commit": "x2"},
            {"project": pd.NA, "commit": "x1"},
            {"project": "lonely", "commit": pd.NA},
            {"project": "lonely", "commit": "x9"},
        ]
    )
    df = pd.concat([df, extra], ignore_index=True)
    a = splits.make_assignments(df, seed=seed)
    assert splits.validate_assignments(a, len(df)) == []
    for col in ("project_key", "commit_key", "group_key"):
        assert a.dropna(subset=[col]).groupby(col)["split"].nunique().max() == 1


def test_shared_commit_links_projects():
    a = splits.make_assignments(synthetic())
    assert a.loc[a["project_key"].isin(["proj_5", "proj_6"]), "split"].nunique() == 1


def test_unknown_project_never_in_holdout():
    rows = [{"project": pd.NA, "commit": f"u{i}"} for i in range(60)]
    rows += [{"project": f"p{i}", "commit": f"c{i}"} for i in range(60)]
    a = splits.make_assignments(_frame(rows))
    assert not ((a["split"] == "holdout") & a["project_key"].isna()).any()


def test_reproducible_for_fixed_seed():
    df = synthetic()
    assert splits.make_assignments(df, seed=7).equals(splits.make_assignments(df, seed=7))


def test_ratios_close_to_target():
    share = splits.make_assignments(synthetic())["split"].value_counts(normalize=True)
    for s, r in splits.RATIOS.items():
        assert abs(share[s] - r) < 0.03


# ------------------------------------------------------------------ CWE handling
def test_feature_matrix_cwe_counts_and_row_alignment():
    df = _frame(
        [
            {"project": "a", "commit": "1", "cwe": ["CWE-79", "CWE-89"]},  # multilabel
            {"project": "b", "commit": "2", "cwe": []},  # vulnerable, no CWE -> NONE
            {"project": "c", "commit": "3", "cwe": ["CWE-79", "CWE-79"]},  # duplicate counted once
            {
                "project": "d",
                "commit": "4",
                "cwe": ["CWE-79"],
                "label": 0,
            },  # negatives never counted
            {"project": "e", "commit": "5", "cwe": None},  # missing CWE -> NONE
        ]
    )
    keys = splits.build_group_keys(df)
    M, names, _uniq, gid = splits._feature_matrix(df, keys)
    assert names == ["rows", "positives", "cwe:CWE-79", "cwe:CWE-89", "cwe:NONE"]
    assert M.sum(axis=0).tolist() == [5, 4, 2, 1, 2]
    assert M[gid[0]].tolist() == [1, 1, 1, 1, 0]  # component of row 0 carries both CWEs
    assert M[gid[3]].tolist() == [1, 0, 0, 0, 0]


def test_no_positive_rows_do_not_crash():
    df = _frame([{"project": f"p{i}", "commit": f"c{i}", "label": 0} for i in range(40)])
    a = splits.make_assignments(df)
    assert splits.validate_assignments(a, len(df)) == []
    assert splits.validate_cwe_distribution(df, a)["per_cwe"] == {}
    assert splits._per_cwe(df, a) == {}


def test_common_cwes_balanced_rare_cwe_reported():
    df = synthetic()
    rep = splits.validate_cwe_distribution(df, splits.make_assignments(df))
    for cwe in COMMON:
        assert cwe not in rep["unavoidable"] and cwe not in rep["residual"], rep["per_cwe"][cwe]
    assert "CWE-999" in rep["unavoidable"]  # only 2 groups for 4 splits
    assert rep["per_cwe"]["CWE-999"]["unavoidable_reasons"]


# ------------------------------------------------------------------ D39
def test_d39_patched_rows_follow_parent_and_are_not_positives():
    rows = [
        {"project": f"p{i}", "commit": f"c{i}", "cwe": ["CWE-89"], "fixed_code": f"fixed{i}"}
        for i in range(60)
    ]
    df, parent, stats = splits.add_patched_negatives(_frame(rows))
    assert stats["added"] == 60 and (df.loc[parent >= 0, "label"] == 0).all()
    a = splits.make_assignments(df, parent)
    derived = np.flatnonzero(parent >= 0)
    assert (a.loc[derived, "split"].to_numpy() == a.loc[parent[derived], "split"].to_numpy()).all()
    assert (
        a.loc[derived, "group_key"].to_numpy() == a.loc[parent[derived], "group_key"].to_numpy()
    ).all()
    assert splits.validate_assignments(a, len(df)) == []
    M, _, _, _ = splits._feature_matrix(df, splits.build_group_keys(df, parent))
    assert M[:, 0].sum() == 120 and M[:, 1].sum() == 60  # negatives add rows, not positives


# ------------------------------------------------------------------ validation
def test_validation_detects_planted_group_and_project_leak():
    df = synthetic()
    a = splits.make_assignments(df)
    g = a.groupby("group_key").size()
    idx = a.index[a["group_key"] == g[g >= 2].index[0]][0]
    a.loc[idx, "split"] = next(s for s in splits.SPLITS if s != a.loc[idx, "split"])
    msg = " ".join(splits.validate_assignments(a, len(df)))
    assert "group leakage" in msg and "project overlap" in msg


def test_validation_detects_commit_leak_alone():
    a = pd.DataFrame(
        {
            "row_id": [0, 1],
            "group_key": ["g:1", "g:2"],
            "group_kind": ["commit"] * 2,
            "project_key": ["p1", "p2"],
            "commit_key": ["same", "same"],
            "parent_row_id": [-1, -1],
            "split": ["train", "val"],
        }
    )
    msg = " ".join(splits.validate_assignments(a, 2))
    assert "commit leakage" in msg and "group leakage" not in msg


def test_validation_detects_missing_and_duplicates():
    df = synthetic()
    a = splits.make_assignments(df)
    broken = pd.concat([a.iloc[1:], a.iloc[[5]]], ignore_index=True)
    msg = " ".join(splits.validate_assignments(broken, len(df)))
    assert "duplicate assignments" in msg and "missing rows" in msg


# ------------------------------------------------------------------ manifest
def _patch_merge(monkeypatch, df):
    monkeypatch.setattr(
        splits.merge,
        "merge_datasets",
        lambda d: (df.copy(), [{"file": "x.parquet", "sha256": "abc"}]),
        raising=False,
    )
    monkeypatch.setattr(splits.merge, "count_cross_source_duplicates", lambda d: 0, raising=False)


def test_build_splits_writes_manifest_with_normalizer(monkeypatch, tmp_path):
    df = synthetic(n_projects=200)
    df["fixed_code"] = pd.Series(
        [f"fix{i}" if lab else pd.NA for i, lab in enumerate(df["label"])], dtype="string"
    )
    interim_dir = tmp_path / "interim"
    interim_dir.mkdir(parents=True)

    schema.to_parquet(df, interim_dir / "merged_datasets.parquet")
    _patch_merge(monkeypatch, df)
    m = splits.build_splits(
        tmp_path / "interim",
        tmp_path / "splits",
        tmp_path / "manifest.json",
        d39_patched_negatives=True,
    )
    on_disk = json.loads((tmp_path / "manifest.json").read_text())
    assert on_disk["project_normalizer"] == splits.NORMALIZER_NAME
    assert on_disk["manifest_version"] == splits.MANIFEST_VERSION
    assert on_disk["d39_negatives"]["added"] > 0
    assert sum(v["rows"] for v in m["splits"].values()) == m["rows_total"]
    assert (
        on_disk["diagnostics"]["canonical_project_names"]
        <= on_disk["diagnostics"]["raw_project_names"]
    )
    assert set(on_disk["cwe_balance"]["targets"]) == set(splits.SPLITS)


def test_build_splits_refuses_to_write_into_interim(monkeypatch, tmp_path):
    _patch_merge(monkeypatch, synthetic(n_projects=50))
    with pytest.raises(splits.SplitValidationError):
        splits.build_splits(tmp_path, tmp_path, tmp_path / "m.json")
