"""Unit tests for list-valued `cve` in the unified schema."""

import numpy as np
import pandas as pd
import pytest

from shield_core.datasets import schema  # adjust if your package path differs
from shield_core.datasets.schema import normalize_cve

# --- normalize_cve -----------------------------------------------------------


def test_single_cve():
    assert normalize_cve("CVE-2015-8467") == ["CVE-2015-8467"]


def test_single_cve_lowercase_and_whitespace():
    assert normalize_cve("  cve-2015-8467 ") == ["CVE-2015-8467"]


@pytest.mark.parametrize(
    "value",
    [
        "CVE-2015-8467, CVE-2016-0001",
        "CVE-2016-0001;CVE-2015-8467",
        "fixes CVE-2015-8467 and cve-2016-0001.",
        ["CVE-2016-0001", "CVE-2015-8467"],
        ("cve-2015-8467", "CVE-2016-0001"),
        {"CVE-2015-8467", "CVE-2016-0001"},
        np.array(["CVE-2016-0001", "CVE-2015-8467"]),
    ],
)
def test_multiple_cves_sorted(value):
    assert normalize_cve(value) == ["CVE-2015-8467", "CVE-2016-0001"]


def test_duplicates_removed_case_insensitive():
    assert normalize_cve("CVE-2015-8467, cve-2015-8467") == ["CVE-2015-8467"]
    assert normalize_cve(["CVE-2015-8467", "cve-2015-8467", "CVE-2015-8467"]) == ["CVE-2015-8467"]


def test_numeric_sort_not_lexicographic():
    assert normalize_cve(["CVE-2015-10000", "CVE-2015-8467", "CVE-2014-99999"]) == [
        "CVE-2014-99999",
        "CVE-2015-8467",
        "CVE-2015-10000",
    ]


@pytest.mark.parametrize("value", [None, float("nan"), pd.NA, "", [], (), np.array([])])
def test_missing_values_give_empty_list(value):
    assert normalize_cve(value) == []


@pytest.mark.parametrize(
    "value",
    ["not a cve", "CVE-15-1", "CVE-2015-123", "CVE2015-8467", 12345, ["foo", None, "bar"]],
)
def test_invalid_values_give_empty_list(value):
    assert normalize_cve(value) == []


def test_invalid_mixed_with_valid():
    assert normalize_cve(["junk", None, "CVE-2015-8467", float("nan")]) == ["CVE-2015-8467"]


# --- conform / validate ------------------------------------------------------


def _frame(cves):
    return pd.DataFrame(
        {
            "code": ["int main(){}"] * len(cves),
            "language": ["python"] * len(cves),
            "label": [1] * len(cves),
            "cve": cves,
        }
    )


def test_conform_produces_lists_and_validates():
    df = schema.conform(
        _frame(
            ["cve-2015-8467", ["CVE-2016-0001", "CVE-2015-8467", "CVE-2015-8467"], None, "junk"]
        ),
        source="test",
    )
    assert df["cve"].tolist() == [
        ["CVE-2015-8467"],
        ["CVE-2015-8467", "CVE-2016-0001"],
        [],
        [],
    ]
    assert schema.validate(df) == []


def test_conform_missing_cve_column():
    df = schema.conform(_frame([None]).drop(columns=["cve"]), source="test")
    assert df["cve"].tolist() == [[]]
    assert schema.validate(df) == []


def test_validate_flags_bad_cve_values():
    df = schema.conform(_frame(["CVE-2015-8467"]), source="test")
    df.at[0, "cve"] = "CVE-2015-8467"  # scalar, not a list
    assert any("cve values must be lists" in p for p in schema.validate(df))

    df.at[0, "cve"] = ["CVE-2015-8467", "bad"]
    assert any("malformed CVE" in p for p in schema.validate(df))

    df.at[0, "cve"] = ["CVE-2015-8467", "CVE-2015-8467"]
    assert any("duplicate CVE" in p for p in schema.validate(df))

    df.at[0, "cve"] = ["CVE-2016-0001", "CVE-2015-8467"]
    assert any("not sorted" in p for p in schema.validate(df))


# --- Parquet / PyArrow -------------------------------------------------------


def test_parquet_roundtrip(tmp_path):
    pytest.importorskip("pyarrow")
    df = schema.conform(
        _frame(["CVE-2015-8467, CVE-2016-0001", None, "CVE-2017-1000"]),
        source="test",
    )
    path = tmp_path / "x.parquet"
    schema.to_parquet(df, path)
    back = schema.from_parquet(path)

    assert back["cve"].tolist() == df["cve"].tolist()
    assert all(isinstance(v, list) for v in back["cve"])
    assert schema.validate(back) == []


def test_parquet_all_empty_cve_keeps_string_list_type(tmp_path):
    pa = pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    df = schema.conform(_frame([None, "junk"]), source="test")
    path = tmp_path / "empty.parquet"
    schema.to_parquet(df, path)

    assert pq.read_schema(path).field("cve").type == pa.list_(pa.string())
    assert schema.from_parquet(path)["cve"].tolist() == [[], []]
