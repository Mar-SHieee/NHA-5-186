import json

import pandas as pd
import pyarrow.parquet as pq

from shield_core.datasets.c_cpp_loaders.megavul_loader import (
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
}
UNKNOWN_EXT = {**VUL, "file_path": "docs/readme.txt"}  # fabricated, for the skip test


def _write(tmp_path, records):
    p = tmp_path / "mv.json"
    p.write_text(json.dumps(records))
    return p


def test_mapping(tmp_path):
    df = load_megavul(_write(tmp_path, [VUL]))
    row = df.iloc[0]
    assert row["code"] == VUL["func_before"]
    assert row["fixed_code"] == VUL["func"]
    assert row["label"] == 1
    assert row["cwe"] == ["CWE-189"]
    assert row["project"] == "qemu"
    assert row["commit"] == VUL["commit_hash"]
    assert row["language"] == "cpp"
    assert row["source"] == "megavul"


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
