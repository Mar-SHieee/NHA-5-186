import pandas as pd

from shield_core.datasets.bigvul_loader import map_to_unified
from shield_core.datasets.schema import conform


def test_bigvul_vulnerable_mapping():
    raw = pd.DataFrame(
        [
            {
                "CVE ID": "CVE-2020-0001",
                "CVE Page": "https://example.com",
                "CWE ID": "CWE-119",
                "codeLink": "https://example.com/code",
                "commit_id": "abc123",
                "commit_message": "fix vulnerability",
                "func_after": "int foo() { return 0; }",
                "func_before": "int foo() { strcpy(a, b); }",
                "lang": "C",
                "project": "test-project",
                "vul": 1,
            }
        ]
    )

    result = conform(map_to_unified(raw), "bigvul")

    assert len(result) == 1

    row = result.iloc[0]

    assert row["code"] == "int foo() { strcpy(a, b); }"
    assert row["fixed_code"] == "int foo() { return 0; }"
    assert row["label"] == 1
    assert row["language"] == "C"
    assert row["cwe"] == ["CWE-119"]
    assert row["project"] == "test-project"
    assert row["commit"] == "abc123"
    assert row["source"] == "bigvul"


def test_bigvul_non_vulnerable_mapping():
    raw = pd.DataFrame(
        [
            {
                "CVE ID": None,
                "CVE Page": None,
                "CWE ID": "CWE-20",
                "codeLink": None,
                "commit_id": "def456",
                "commit_message": "normal commit",
                "func_after": "int bar() { return 1; }",
                "func_before": "int bar() { return 2; }",
                "lang": "C",
                "project": "test-project",
                "vul": 0,
            }
        ]
    )

    result = conform(map_to_unified(raw), "bigvul")

    assert len(result) == 1

    row = result.iloc[0]

    assert row["code"] == "int bar() { return 1; }"
    assert pd.isna(row["fixed_code"])
    assert row["label"] == 0
    assert row["language"] == "C"
    assert row["cwe"] == ["CWE-20"]
    assert row["project"] == "test-project"
    assert row["commit"] == "def456"
    assert row["source"] == "bigvul"


def test_bigvul_mapping_does_not_modify_raw_data():
    raw = pd.DataFrame(
        [
            {
                "CVE ID": "CVE-2020-0001",
                "CVE Page": "https://example.com",
                "CWE ID": "CWE-119",
                "codeLink": "https://example.com/code",
                "commit_id": "abc123",
                "commit_message": "fix vulnerability",
                "func_after": "fixed",
                "func_before": "vulnerable",
                "lang": "C",
                "project": "test-project",
                "vul": 1,
            }
        ]
    )

    original = raw.copy(deep=True)

    map_to_unified(raw)

    pd.testing.assert_frame_equal(raw, original)
