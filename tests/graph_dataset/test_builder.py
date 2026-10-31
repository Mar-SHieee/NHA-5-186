"""Small cache-to-tensor builder integration using only local fixtures."""

import pandas as pd
import pytest

pytest.importorskip("torch_geometric")

from shield_core.extraction.cache import CacheKey
from shield_core.graph_dataset import builder
from shield_core.graph_dataset.builder import build_cwe_vocab, build_split
from shield_core.graph_dataset.dataset import ShieldGraphDataset
from shield_core.graph_dataset.schema import ConverterConfig


class FakeExtractor:
    name = "joern"
    version = "4.0.647"
    schema_version = "0.1-draft"


class MemoryCache:
    def __init__(self, graphs):
        self.graphs = graphs

    def get(self, key):
        return self.graphs.get(key.code_sha)


def test_split_builder_records_cache_misses_and_labels(tmp_path, load_graph):
    code1, code2, missing, empty = (
        "def one(): return 1",
        "def two(): return 2",
        "def none(): pass",
        "",
    )
    table = pd.DataFrame(
        {
            "code": [code1, code2, missing, empty],
            "language": ["python"] * 4,
            "label": [1, 0, 1, 0],
            "cwe": [["CWE-1"], [], ["CWE-2"], []],
        }
    )
    path = tmp_path / "train.parquet"
    table.to_parquet(path)
    extractor = FakeExtractor()
    cache = MemoryCache(
        {
            CacheKey.for_code(code1, "python", extractor).code_sha: load_graph("get_user_py"),
            CacheKey.for_code(code2, "python", extractor).code_sha: load_graph("branch_py"),
        }
    )
    vocab = build_cwe_vocab(path, "python")
    result = build_split(path, "python", ConverterConfig(), cache, extractor, cwe_vocab=vocab)
    assert vocab == ["CWE-1", "CWE-2"]
    assert [r["status"] for r in result.rows] == ["ok", "ok", "no_graph_in_cache", "bad_code"]
    assert len(result.data_list) == 2
    assert result.data_list[0].y.tolist() == [1]
    assert result.data_list[0].cwe_multihot.tolist() == [[1.0, 0.0]]
    processed = tmp_path / "processed"
    processed.mkdir()
    builder._atomic_save(processed / "train.pt", result.data_list)
    dataset = ShieldGraphDataset(tmp_path, "train")
    assert len(dataset) == 2
    assert dataset.num_node_features == 15


def test_build_all_writes_versioned_outputs_and_protects_existing(
    tmp_path, monkeypatch, load_graph
):
    import shield_core.paths as paths

    split_dir = tmp_path / "splits"
    split_dir.mkdir()
    code = "def fixture(): return 1"
    pd.DataFrame(
        {"code": [code], "language": ["python"], "label": [1], "cwe": [["CWE-1"]]}
    ).to_parquet(split_dir / "train.parquet")
    extractor = FakeExtractor()
    memory = MemoryCache(
        {CacheKey.for_code(code, "python", extractor).code_sha: load_graph("get_user_py")}
    )
    monkeypatch.setattr(paths, "SPLITS_DIR", split_dir)
    monkeypatch.setattr(builder, "GraphCache", lambda: memory)
    root = builder.build_all(
        "python", ConverterConfig(), splits=("train",), out_root=tmp_path / "out"
    )
    assert (root / "config.json").is_file()
    assert (root / "pyg_dataset_report.md").is_file()
    assert len(ShieldGraphDataset(root, "train")) == 1
    with pytest.raises(FileExistsError):
        builder.build_all("python", ConverterConfig(), splits=("train",), out_root=tmp_path / "out")


def test_limit_counts_only_requested_language_rows(tmp_path, load_graph):
    code = "def target(): return 1"
    path = tmp_path / "mixed.parquet"
    pd.DataFrame(
        {
            "code": ["int other;", code],
            "language": ["cpp", "python"],
            "label": [0, 1],
            "cwe": [[], ["CWE-1"]],
        }
    ).to_parquet(path)
    extractor = FakeExtractor()
    cache = MemoryCache(
        {CacheKey.for_code(code, "python", extractor).code_sha: load_graph("get_user_py")}
    )
    result = build_split(path, "python", ConverterConfig(), cache, extractor, limit=1)
    assert len(result.rows) == 1
    assert result.rows[0]["row"] == 1
    assert result.rows[0]["status"] == "ok"
