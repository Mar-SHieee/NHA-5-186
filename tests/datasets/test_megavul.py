import json

import pandas as pd
import pyarrow.parquet as pq

from shield_core.datasets.loaders.megavul_loader import (
    _language,
    _project,
    _to_row,
    load_megavul,
    megavul_to_parquet,
)
from shield_core.datasets.schema import COLUMNS

VUL = {
    "cwe_ids": ["CWE-189"],
    "repo_name": "qemu",
    "commit_hash": "fe3c546c5ff2a6210f9a4d8561cc64051ca8603e",
    "file_path": "hw/usb/dev-network.c",
    "func_before": "int f(){ if (a + b > c) return 1; }",
    "func": "int f(){ if (b > c || a >= c || a + b > c) { return 1; } }",
    "is_vul": True,
    "cve_id": "CVE-2023-1234",
    "git_url": "https://github.com/qemu/qemu/commit/fe3c546",
}

NON_VUL = {
    "cwe_ids": [],
    "repo_name": "qemu",
    "commit_hash": "abcd1234",
    "file_path": "hw/usb/dev-network.c",
    "func_before": "old",
    "func": "new_fixed",
    "is_vul": False,
    "cve_id": None,
    "git_url": None,
}

UNKNOWN_EXT = {**VUL, "file_path": "docs/readme.txt"}


def _write(tmp_path, records):
    p = tmp_path / "mv.json"
    p.write_text(json.dumps(records))
    return p


def test_language_detection():
    assert _language("foo.c") == "cpp"
    assert _language("foo.CPP") == "cpp"
    assert _language("foo.h") == "cpp"
    assert _language("Foo.java") == "java"
    assert _language("docs/readme.txt") is None
    assert _language(None) is None
    assert _language("") is None


def test_project_from_git_url_and_fallback():
    rec = {"git_url": "https://github.com/qemu/qemu/commit/abc", "repo_name": "qemu"}
    assert _project(rec) == "qemu/qemu"
    rec2 = {"git_url": None, "repo_name": "qemu"}
    assert _project(rec2) == "qemu"
    rec3 = {"git_url": "https://gitlab.com/a/b/commit/abc", "repo_name": "myrepo"}
    assert _project(rec3) == "myrepo"


def test_to_row_vul_and_non_vul():
    row = _to_row(VUL)
    assert row["code"] == VUL["func_before"]
    assert row["fixed_code"] == VUL["func"]
    assert row["label"] == 1
    assert row["cwe"] == ["CWE-189"]
    assert row["language"] == "cpp"

    row2 = _to_row(NON_VUL)
    assert row2["code"] == NON_VUL["func"]
    assert row2["fixed_code"] is None
    assert row2["label"] == 0
    assert row2["cwe"] is None

    assert _to_row(UNKNOWN_EXT) is None


def test_mapping(tmp_path):
    df = load_megavul(_write(tmp_path, [VUL]))
    row = df.iloc[0]
    assert row["code"] == VUL["func_before"]
    assert row["fixed_code"] == VUL["func"]
    assert row["label"] == 1
    assert row["cwe"] == ["CWE-189"]
    assert row["project"] in ("qemu", "qemu/qemu")
    assert row["commit"] == VUL["commit_hash"]
    assert row["language"] == "cpp"
    assert row["source"] == "megavul"
    assert list(df.columns) == COLUMNS


def test_mapping_without_git_url(tmp_path):
    rec = {**VUL, "git_url": None}
    df = load_megavul(_write(tmp_path, [rec]))
    assert df.iloc[0]["project"] == "qemu"


def test_unknown_extension_is_skipped(tmp_path):
    df = load_megavul(_write(tmp_path, [VUL, UNKNOWN_EXT]))
    assert len(df) == 1


def test_limit(tmp_path):
    df = load_megavul(_write(tmp_path, [VUL, VUL, VUL]), limit=2)
    assert len(df) == 2


def test_chunked_parquet(tmp_path):
    src = _write(tmp_path, [VUL, VUL, UNKNOWN_EXT, VUL])
    out = tmp_path / "out.parquet"

    stats = megavul_to_parquet(src, out, chunk_size=2)

    df = pd.read_parquet(out)

    assert list(df.columns) == COLUMNS
    assert len(df) == 3
    assert stats["rows"] == 3
    assert stats["skipped_unknown_language"] == 1
    assert pq.ParquetFile(out).num_row_groups == 2
    assert not (tmp_path / "out.parquet.tmp").exists()
    mapping = tmp_path / "out_commit_cve_mapping.parquet"
    assert mapping.exists()
    assert stats["commit_cve_links"] >= 1


def test_commit_cve_mapping_content(tmp_path):
    rec = {**VUL, "cve_id": "CVE-2023-1234, CVE-2022-5678"}
    src = _write(tmp_path, [rec])
    out = tmp_path / "out.parquet"
    megavul_to_parquet(src, out, chunk_size=10)
    mapping_path = tmp_path / "out_commit_cve_mapping.parquet"
    mdf = pd.read_parquet(mapping_path)
    assert len(mdf) == 2
    assert set(mdf["cve"]) == {"CVE-2023-1234", "CVE-2022-5678"}
