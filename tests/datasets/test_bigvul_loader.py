"""Tests for the Big-Vul loader mapping and commit-CVE extraction."""

import pandas as pd

import shield_core.datasets.loaders.bigvul_loader as bigvul_loader
from shield_core.datasets.schema import conform


def _raw_row(**overrides):
    row = {
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
    row.update(overrides)
    return row


def test_bigvul_vulnerable_mapping():
    raw = pd.DataFrame([_raw_row()])

    result = conform(bigvul_loader.map_to_unified(raw), "bigvul")

    assert len(result) == 1
    row = result.iloc[0]

    assert row["code"] == "int foo() { strcpy(a, b); }"
    assert row["fixed_code"] == "int foo() { return 0; }"
    assert row["label"] == 1
    assert row["language"] == "cpp"
    assert row["cwe"] == ["CWE-119"]
    assert row["project"] == "test-project"
    assert row["commit"] == "abc123"
    assert row["source"] == "bigvul"


def test_bigvul_non_vulnerable_mapping():
    raw = pd.DataFrame(
        [
            _raw_row(
                **{
                    "CVE ID": None,
                    "CVE Page": None,
                    "CWE ID": "CWE-20",
                    "codeLink": None,
                    "commit_id": "def456",
                    "commit_message": "normal commit",
                    "func_after": "int bar() { return 1; }",
                    "func_before": "int bar() { return 2; }",
                    "vul": 0,
                }
            )
        ]
    )

    result = conform(bigvul_loader.map_to_unified(raw), "bigvul")

    assert len(result) == 1
    row = result.iloc[0]

    assert row["code"] == "int bar() { return 1; }"
    assert pd.isna(row["fixed_code"])
    assert row["label"] == 0
    assert row["language"] == "cpp"
    assert row["cwe"] == ["CWE-20"]
    assert row["project"] == "test-project"
    assert row["commit"] == "def456"
    assert row["source"] == "bigvul"


def test_bigvul_resolves_project_from_github_commit_url():
    raw = pd.DataFrame(
        [
            _raw_row(
                codeLink="https://github.com/example-owner/example-repo/commit/abc123",
                project="raw-project-name",
            )
        ]
    )

    result = conform(bigvul_loader.map_to_unified(raw), "bigvul")

    assert result.loc[0, "project"] == "example-owner/example-repo"


def test_bigvul_falls_back_to_raw_project_without_github_url():
    raw = pd.DataFrame(
        [
            _raw_row(
                codeLink="https://git.kernel.org/pub/scm/example/repo.git",
                project="raw-project-name",
            )
        ]
    )

    result = conform(bigvul_loader.map_to_unified(raw), "bigvul")

    assert result.loc[0, "project"] == "raw-project-name"


def test_bigvul_supports_target_column_alias():
    raw = pd.DataFrame([_raw_row(target=1)])
    raw = raw.drop(columns=["vul"])

    result = conform(bigvul_loader.map_to_unified(raw), "bigvul")

    assert result.loc[0, "label"] == 1
    assert result.loc[0, "code"] == "int foo() { strcpy(a, b); }"


def test_bigvul_mapping_does_not_modify_raw_data():
    raw = pd.DataFrame([_raw_row()])
    original = raw.copy(deep=True)

    bigvul_loader.map_to_unified(raw)

    pd.testing.assert_frame_equal(raw, original)


def test_bigvul_commit_cve_mapping_extracts_unique_pairs(tmp_path, monkeypatch):
    raw_path = tmp_path / "bigvul_full.parquet"
    mapping_path = tmp_path / "bigvul_commit_cve_mapping.parquet"
    interim_dir = tmp_path / "interim"

    raw = pd.DataFrame(
        {
            "commit_id": ["abc123", "abc123", "def456", None, "ghi789"],
            "CVE ID": [
                "CVE-2020-0001, CVE-2021-12345",
                "CVE-2020-0001",
                "CVE-2022-0002",
                "CVE-2023-0003",
                "",
            ],
        }
    )
    raw.to_parquet(raw_path, index=False)

    monkeypatch.setattr(bigvul_loader, "FULL_PATH", raw_path)
    monkeypatch.setattr(bigvul_loader, "MAPPING_PATH", mapping_path)
    monkeypatch.setattr(bigvul_loader, "INTERIM_DIR", interim_dir)

    bigvul_loader.save_commit_cve_mapping()

    result = pd.read_parquet(mapping_path)
    actual_pairs = set(zip(result["commit"], result["cve"], strict=True))

    assert actual_pairs == {
        ("abc123", "CVE-2020-0001"),
        ("abc123", "CVE-2021-12345"),
        ("def456", "CVE-2022-0002"),
    }
    assert len(result) == 3
