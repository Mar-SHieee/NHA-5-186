import pandas as pd
import pytest

from shield_core.datasets.python_loaders.cvefixes_python_loaders import CVEfixesPythonLoader
from shield_core.datasets.schema import COLUMNS

# ---------- toy CVEfixes tables ----------
# fc1 (h1, Python): a() old+new, b() old only, c() new only
# fc2 (h2, Python): d() old is blank, f() old == new (not a real fix)
# fc3 (h3, C): must be filtered out
METHOD_CHANGE = pd.DataFrame(
    {
        "method_change_id": range(1, 10),
        "file_change_id": [1, 1, 1, 1, 2, 2, 2, 2, 3],
        "name": ["a", "a", "b", "c", "d", "d", "f", "f", "e"],
        "signature": ["a()", "a()", "b()", "c()", "d()", "d()", "f()", "f()", "e()"],
        "code": [
            "def a(): return 1",
            "def a(): return 2",
            "def b(): pass",
            "def c(): pass",
            "   ",
            "def d(): ok",
            "def f(): x",
            "def f(): x",
            "def e(): pass",
        ],
        "before_change": [True, False, True, False, True, False, True, False, True],
    }
)
FILE_CHANGE = pd.DataFrame(
    {
        "file_change_id": [1, 2, 3],
        "hash": ["h1", "h2", "h3"],
        "filename": ["a.py", "b.py", "c.c"],
        "programming_language": ["Python", "Python", "C"],
    }
)
COMMITS = pd.DataFrame(
    {
        "hash": ["h1", "h2"],
        "repo_url": ["https://github.com/org/proj", "https://github.com/org/other.git"],
        "author_date": ["2020-01-01 10:00:00-04:00", "2021-06-05 08:30:00+02:00"],
        "author": ["x", "y"],
    }
)
FIXES = pd.DataFrame(
    {
        "cve_id": ["CVE-1", "CVE-2", "CVE-3"],
        "hash": ["h1", "h1", "h2"],
        "repo_url": ["u", "u", "v"],
    }
)
CWE_CLASSIFICATION = pd.DataFrame(
    {
        "cve_id": ["CVE-1", "CVE-2", "CVE-3"],
        "cwe_id": ["CWE-79", "CWE-20", "NVD-CWE-Other"],
    }
)


@pytest.fixture
def loader(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    METHOD_CHANGE.to_csv(raw / "method_change.csv", index=False)
    FILE_CHANGE.to_csv(raw / "file_change.csv", index=False)
    COMMITS.to_csv(raw / "commits.csv", index=False)
    FIXES.to_csv(raw / "fixes.csv", index=False)
    CWE_CLASSIFICATION.to_csv(raw / "cwe_classification.csv", index=False)
    return CVEfixesPythonLoader(raw_dir=raw, interim_dir=tmp_path / "interim")


@pytest.fixture
def merged(loader):
    """Output of _merge_tables on the toy data."""
    return loader._merge_tables(loader._load_tables())


# ---------- reading ----------


def test_load_single_csv_keeps_only_needed_columns(loader):
    df = loader._load_single_csv("method_change")
    assert set(df.columns) == {"file_change_id", "signature", "code", "before_change"}


def test_missing_csv_gives_clear_error(tmp_path):
    loader = CVEfixesPythonLoader(raw_dir=tmp_path, interim_dir=tmp_path)
    with pytest.raises(FileNotFoundError, match="extraction"):
        loader._load_single_csv("commits")


def test_load_tables_returns_all_five(loader):
    assert set(loader._load_tables()) == set(CVEfixesPythonLoader.TABLE_COLUMNS)


# ---------- helpers ----------


def test_to_bool_handles_bool_and_text():
    series = pd.Series([True, False, "True", "false", " TRUE "])
    assert CVEfixesPythonLoader._to_bool(series).tolist() == [True, False, True, False, True]


def test_has_text():
    series = pd.Series(["code", "   ", "", None, pd.NA])
    assert CVEfixesPythonLoader._has_text(series).tolist() == [True, False, False, False, False]


def test_join_cwe_sorts_by_number_and_removes_duplicates():
    ids = pd.Series(["CWE-119", "CWE-20", "CWE-20"])
    assert CVEfixesPythonLoader._join_cwe(ids) == "CWE-20, CWE-119"


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://github.com/org/proj", "proj"),
        ("https://github.com/org/proj.git", "proj"),
        ("https://github.com/org/proj/", "proj"),
        (None, None),
        (float("nan"), None),
    ],
)
def test_project_name(url, expected):
    assert CVEfixesPythonLoader._project_name(url) == expected


# ---------- merging ----------


def test_pair_old_with_new(loader):
    out = loader._pair_old_with_new(loader._load_single_csv("method_change"))
    assert list(out.columns) == ["file_change_id", "code", "fixed_code"]
    assert len(out) == 5  # one row per old function (a, b, d, f, e)
    a = out[out["code"] == "def a(): return 1"].iloc[0]
    assert a["fixed_code"] == "def a(): return 2"
    b = out[out["code"] == "def b(): pass"].iloc[0]
    assert pd.isna(b["fixed_code"])  # no patched version found


def test_new_only_functions_are_not_paired(loader):
    out = loader._pair_old_with_new(loader._load_single_csv("method_change"))
    assert "def c(): pass" not in out["code"].tolist()


def test_aggregate_cwe_per_commit(loader):
    tables = loader._load_tables()
    out = loader._aggregate_cwe_per_commit(tables["fixes"], tables["cwe_classification"])
    cwe = dict(zip(out["hash"], out["cwe"], strict=True))
    assert cwe["h1"] == "CWE-20, CWE-79"  # two CVEs on the same commit
    assert "h2" not in cwe  # only an NVD placeholder


def test_prepare_commits_removes_duplicate_hashes(loader):
    commits = pd.concat([COMMITS, COMMITS.iloc[[0]]], ignore_index=True)
    assert len(loader._prepare_commits(commits)) == 2


def test_merge_tables_does_not_duplicate_functions(merged):
    assert len(merged) == 5
    assert {"hash", "programming_language", "repo_url", "author_date", "cwe"} <= set(merged.columns)


def test_merge_tables_fails_loudly_on_duplicate_file_change_id(loader):
    tables = loader._load_tables()
    tables["file_change"] = pd.concat([tables["file_change"]] * 2, ignore_index=True)
    with pytest.raises(pd.errors.MergeError):
        loader._merge_tables(tables)


# ---------- cleaning ----------


def test_blank_identical_fixes():
    df = pd.DataFrame({"code": ["x", "y"], "fixed_code": ["x", "z"]})
    out = CVEfixesPythonLoader()._blank_identical_fixes(df)
    assert pd.isna(out["fixed_code"].iloc[0])
    assert out["fixed_code"].iloc[1] == "z"


def test_rename_columns(loader, merged):
    out = loader._rename_columns(merged)
    assert {"commit", "language", "project", "date"} <= set(out.columns)


def test_clean_project_names(loader, merged):
    out = loader._clean_project_names(loader._rename_columns(merged))
    assert set(out["project"].dropna()) == {"proj", "other"}


def test_filter_python_only(loader, merged):
    out = loader._filter_python_only(loader._rename_columns(merged))
    assert len(out) == 4  # the C function is gone
    assert out["language"].str.lower().eq("python").all()


def test_normalize_language(loader):
    df = pd.DataFrame({"language": ["Python", "PYTHON"]})
    assert set(loader._normalize_language(df)["language"]) == {"python"}


def test_drop_empty_code(loader):
    df = pd.DataFrame({"code": ["def a(): pass", "   ", None, ""]})
    assert loader._drop_empty_code(df)["code"].tolist() == ["def a(): pass"]


# ---------- samples ----------


def test_create_vulnerable_samples():
    df = pd.DataFrame({"code": ["x"], "fixed_code": ["y"]})
    out = CVEfixesPythonLoader()._create_vulnerable_samples(df)
    assert out["label"].tolist() == [1]
    assert out["fixed_code"].tolist() == ["y"]


def test_create_safe_samples():
    df = pd.DataFrame(
        {"code": ["old1", "old2"], "fixed_code": ["new1", pd.NA], "cwe": ["CWE-79", "CWE-79"]}
    )
    out = CVEfixesPythonLoader()._create_safe_samples(df)
    assert out["code"].tolist() == ["new1"]  # no patched version, no safe sample1
    assert out["label"].tolist() == [0]
    assert out["fixed_code"].isna().all()
    assert out["cwe"].isna().all()


def test_concat_samples():
    a = pd.DataFrame({"code": ["x"], "label": [1]})
    b = pd.DataFrame({"code": ["y"], "label": [0]})
    out = CVEfixesPythonLoader()._concat_samples(a, b)
    assert out["label"].tolist() == [1, 0]
    assert out.index.tolist() == [0, 1]


# ---------- schema and saving ----------


def test_validate_schema_raises_on_bad_label(loader):
    df = pd.DataFrame(
        {
            "code": ["def a(): pass"],
            "language": ["python"],
            "label": [5],
            "source": ["cvefixes_python"],
        }
    )
    with pytest.raises(ValueError, match="failed validation"):
        loader._validate_schema(loader._apply_schema(df))


def test_save_to_parquet(loader):
    df = pd.DataFrame({"code": ["x"], "label": [1]})
    path = loader._save_to_parquet(df)
    assert path.name == "cvefixes_python.parquet"
    assert path.exists()


# ---------- full pipeline ----------


def test_execute_pipeline_end_to_end(loader):
    path = loader.execute_pipeline()
    out = pd.read_parquet(path)

    assert list(out.columns) == COLUMNS
    assert set(out["language"]) == {"python"}
    assert set(out["source"]) == {"cvefixes_python"}

    # vulnerable: a, b, f (d is blank, e is C). safe: only the patched a().
    assert len(out) == 4
    assert (out["label"] == 1).sum() == 3
    assert (out["label"] == 0).sum() == 1

    safe = out[out["label"] == 0].iloc[0]
    assert safe["code"] == "def a(): return 2"
    assert pd.isna(safe["fixed_code"])
    assert len(safe["cwe"]) == 0

    vuln_a = out[out["code"] == "def a(): return 1"].iloc[0]
    assert vuln_a["fixed_code"] == "def a(): return 2"
    assert vuln_a["project"] == "proj"
    assert vuln_a["commit"] == "h1"
    assert "CWE-20" in vuln_a["cwe"]
    assert "CWE-79" in vuln_a["cwe"]  # h1 has CWE-20 and CWE-79

    vuln_f = out[out["code"] == "def f(): x"].iloc[0]
    assert pd.isna(vuln_f["fixed_code"])  # identical code is not a fix
    assert len(vuln_f["cwe"]) == 0  # h2 only has an NVD placeholder
