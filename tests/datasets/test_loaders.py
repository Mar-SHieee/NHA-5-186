"""
Test for the 5 SHIELD loaders:
- megavul
- bigvul
- cvefixes_python
- cvefixes_cpp
- zenodo_python
"""

import json
from pathlib import Path

import pandas as pd

from shield_core.datasets.schema import COLUMNS, conform, validate


# ============== MegaVul ==============
def test_megavul_loader_mapping(tmp_path):
    from shield_core.datasets.loaders.megavul_loader import (
        _language,
        _project,
        load_megavul,
    )

    # language detection
    assert _language("a.c") == "cpp"
    assert _language("a.java") == "java"
    assert _language("a.txt") is None

    # project extraction
    assert (
        _project({"git_url": "https://github.com/qemu/qemu/commit/abc", "repo_name": "qemu"})
        == "qemu/qemu"
    )
    assert _project({"git_url": None, "repo_name": "qemu"}) == "qemu"

    # full load
    rec = {
        "cwe_ids": ["CWE-79"],
        "repo_name": "qemu",
        "commit_hash": "abc123",
        "file_path": "x.c",
        "func_before": "vul()",
        "func": "fixed()",
        "is_vul": True,
        "cve_id": "CVE-2023-0001",
        "git_url": None,
    }
    p = tmp_path / "mv.json"
    p.write_text(json.dumps([rec]))
    df = load_megavul(p)
    assert list(df.columns) == COLUMNS
    assert df.iloc[0]["label"] == 1
    assert df.iloc[0]["source"] == "megavul"
    assert validate(df) == []


# ============== BigVul ==============
def test_bigvul_loader_mapping():
    from shield_core.datasets.loaders.bigvul_loader import (
        COLUMN_ALIASES,
        map_to_unified,
    )

    raw = pd.DataFrame(
        {
            COLUMN_ALIASES.get("func_before", "func_before"): ["int vul(){return 1;}"],
            COLUMN_ALIASES.get("func_after", "func_after"): ["int fixed(){return 0;}"],
            COLUMN_ALIASES.get("target", "target"): [1],
            COLUMN_ALIASES.get("cwe", "CWE ID"): ["CWE-79"],
            COLUMN_ALIASES.get("project", "project"): ["myproj"],
            COLUMN_ALIASES.get("commit", "commit_id"): ["deadbeef"],
            COLUMN_ALIASES.get("date", "Publish Date"): ["2023-01-01"],
            COLUMN_ALIASES.get("lang", "lang"): ["C"],
            COLUMN_ALIASES.get("cve", "CVE ID"): ["CVE-2023-0001"],
            COLUMN_ALIASES.get("repo_link", "codeLink"): [
                "https://github.com/torvalds/linux/commit/abc123"
            ],
        }
    )

    mapped = map_to_unified(raw)
    df = conform(mapped, "bigvul")
    assert list(df.columns) == COLUMNS
    assert validate(df) == []
    # الـ project لازم يجي من اللينك
    assert df.iloc[0]["project"] == "torvalds/linux"


# ============== CVEfixes Python ==============
def test_cvefixes_python_loader():
    from shield_core.datasets.loaders.cvefixes_python_loaders import (
        CVEfixesPythonLoader,
    )

    loader = CVEfixesPythonLoader(raw_dir=Path("/tmp/nonexist"), interim_dir=Path("/tmp"))

    s = pd.Series(["True", "false", "True "])
    assert loader._to_bool(s).tolist() == [True, False, True]

    s2 = pd.Series(["  code  ", "", None])
    assert loader._has_text(s2).tolist() == [True, False, False]

    mc = pd.DataFrame(
        {
            "file_change_id": [1, 1],
            "signature": ["foo()", "foo()"],
            "code": ["old", "new"],
            "before_change": [True, False],
        }
    )
    paired = loader._pair_old_with_new(mc)
    assert paired.iloc[0]["code"] == "old"
    assert paired.iloc[0]["fixed_code"] == "new"

    df = pd.DataFrame({"language": ["Python", "python", "C"]})
    filtered = loader._filter_python_only(df)
    assert len(filtered) == 2


# ============== CVEfixes C++ ==============
def test_cvefixes_cpp_loader():
    from shield_core.datasets.loaders.cvefixes_cpp_loaders import (
        CVEfixesCppLoader,
    )

    loader = CVEfixesCppLoader(raw_dir=Path("/tmp/nonexist"), interim_dir=Path("/tmp"))

    s = pd.Series(["True", "False"])
    assert loader._to_bool(s).tolist() == [True, False]

    df = pd.DataFrame({"code": ["a", "b"], "fixed_code": ["a", "c"]})
    out = loader._blank_identical_fixes(df)
    assert pd.isna(out.iloc[0]["fixed_code"])
    assert out.iloc[1]["fixed_code"] == "c"

    df2 = pd.DataFrame({"language": ["c", "C++", "python"]})
    filtered = loader._filter_c_cpp_only(df2)
    assert len(filtered) == 2


# ============== Zenodo Python ==============
def test_zenodo_python_loader_build_mapping():
    from shield_core.datasets.loaders.zenodo_python_loader import (
        build_commit_cve_mapping,
    )

    raw = pd.DataFrame(
        {
            "repo_url": ["https://github.com/pallets/flask"],
            "committer_date": ["2023-01-01"],
            "cve_id": ["CVE-2023-1234"],
            "commit": ["abc123"],
        }
    )
    mapping = build_commit_cve_mapping(raw)
    assert "project" in mapping.columns
    assert "commit" in mapping.columns
    assert "cve" in mapping.columns
    assert mapping.iloc[0]["cve"] == "CVE-2023-1234"


def test_all_loaders_conform_to_schema():
    from shield_core.datasets.schema import arrow_schema

    schema = arrow_schema()
    assert set(schema.names) == set(COLUMNS)
