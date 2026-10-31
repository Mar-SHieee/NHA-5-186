"""Build split-level tensors from parquet rows and an existing raw graph cache."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

from shield_core.extraction.cache import CacheKey, GraphCache
from shield_core.extraction.graph_extractor import code_sha256
from shield_core.extraction.joern_extractor import JoernExtractor
from shield_core.graph_dataset.filtering import filter_graph
from shield_core.graph_dataset.schema import CONVERTER_VERSION, ConverterConfig
from shield_core.graph_dataset.to_pyg import to_data


@dataclass
class BuildResult:
    data_list: list
    rows: list[dict]


def _cwes(value) -> list[str]:
    if value is None:
        return []
    return sorted({str(x) for x in value if x}) if not isinstance(value, str) else [value]


def _sha256_file(path: Path) -> str:
    """Hash large parquet inputs incrementally so build provenance is memory-safe."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_cwe_vocab(train_path: Path | str, language: str) -> list[str]:
    """Fit a deterministic CWE vocabulary from vulnerable training rows only."""
    values = set()
    for batch in pq.ParquetFile(train_path).iter_batches(columns=["language", "label", "cwe"]):
        table = batch.to_pydict()
        for lang, label, cwes in zip(table["language"], table["label"], table["cwe"], strict=True):
            if lang == language and int(label) == 1:
                values.update(_cwes(cwes))
    return sorted(values)


def build_split(
    split_path: Path | str,
    language: str,
    config: ConverterConfig,
    cache: GraphCache,
    key_extractor=None,
    *,
    cwe_vocab: list[str] | None = None,
    limit: int | None = None,
) -> BuildResult:
    """Convert rows in original order while keeping a report row for every input row."""
    extractor = key_extractor or JoernExtractor(docker_image="shield-joern")
    vocab = cwe_vocab or []
    lookup = {v: i for i, v in enumerate(vocab)}
    result, reports, seen = [], [], set()
    parquet = pq.ParquetFile(split_path)
    row_index = 0
    for batch in parquet.iter_batches(columns=["code", "language", "label", "cwe"]):
        values = batch.to_pydict()
        for code, lang, label, cwes in zip(
            values["code"], values["language"], values["label"], values["cwe"], strict=True
        ):
            current = row_index
            row_index += 1
            sha = code_sha256(code) if isinstance(code, str) else ""
            row = {
                "row": current,
                "code_sha": sha,
                "label": int(label),
                "cwe": _cwes(cwes),
                "status": "other_language" if lang != language else "bad_code",
                "n_nodes_raw": 0,
                "n_edges_raw": 0,
                "n_nodes": 0,
                "n_edges": 0,
                "usable": False,
                "has_real_method": False,
                "n_unknown": 0,
                "unknown_share": 0.0,
                "n_cfg": 0,
                "n_reaching_def": 0,
                "n_meta_class_adapter": 0,
                "edge_counts": {},
            }
            if limit is not None and len(reports) >= limit:
                break
            if lang != language:
                reports.append(row)
                continue
            if not isinstance(code, str) or not code.strip():
                reports.append(row)
                continue
            if sha in seen:
                row["status"] = "duplicate_code"
                reports.append(row)
                continue
            seen.add(sha)
            graph = cache.get(CacheKey.for_code(code, language, extractor))
            if graph is None:
                row["status"] = "no_graph_in_cache"
                reports.append(row)
                continue
            filtered = filter_graph(graph, config)
            diag = filtered.diagnostics
            row.update(
                n_nodes_raw=diag.n_nodes_raw,
                n_edges_raw=diag.n_edges_raw,
                n_nodes=diag.n_nodes,
                n_edges=diag.n_edges,
                usable=diag.usable,
                has_real_method=diag.has_real_method,
                n_unknown=diag.n_unknown,
                unknown_share=diag.unknown_share,
                n_cfg=diag.n_cfg,
                n_reaching_def=diag.n_reaching_def,
                n_meta_class_adapter=diag.n_meta_class_adapter,
                edge_counts=diag.edge_counts,
                status=filtered.reason,
            )
            if filtered.graph is not None:
                import numpy as np

                multi = np.zeros(len(vocab), dtype=np.float32)
                unseen = []
                for cwe in row["cwe"]:
                    if cwe in lookup:
                        multi[lookup[cwe]] = 1
                    else:
                        unseen.append(cwe)
                row["unseen_cwe"] = unseen
                result.append(
                    to_data(
                        filtered.graph,
                        y=row["label"],
                        cwe_multihot=multi,
                        code_sha=sha,
                        row=current,
                    )
                )
            reports.append(row)
        if limit is not None and len(reports) >= limit:
            break
    return BuildResult(result, reports)


def build_all(
    language: str,
    config: ConverterConfig,
    splits=("train", "val", "test", "holdout"),
    limit=None,
    out_root=None,
    overwrite=False,
) -> Path:
    """Write a versioned dataset folder; all output files are generated atomically."""
    from shield_core.paths import PYG_DATASET_DIR, SPLITS_DIR

    root = (
        Path(out_root or PYG_DATASET_DIR)
        / CONVERTER_VERSION
        / "0.1-draft"
        / language
        / config.fingerprint()
    )
    if root.exists() and any(root.iterdir()) and not overwrite:
        raise FileExistsError(f"{root} already contains a build; pass overwrite=True")
    root.mkdir(parents=True, exist_ok=True)
    cache = GraphCache()
    vocab = build_cwe_vocab(SPLITS_DIR / "train.parquet", language)
    summary = {}
    all_rows = []
    rule_b_rows = []
    split_hashes = {}
    extractor = JoernExtractor(docker_image="shield-joern")
    for split in splits:
        split_path = SPLITS_DIR / f"{split}.parquet"
        if not split_path.exists():
            continue
        split_hashes[split] = _sha256_file(split_path)
        built = build_split(
            split_path, language, config, cache, extractor, cwe_vocab=vocab, limit=limit
        )
        all_rows.extend(built.rows)
        if config.stub_rule == "A":
            rule_b = build_split(
                split_path,
                language,
                ConverterConfig(
                    stub_rule="B",
                    max_nodes=config.max_nodes,
                    edge_types=config.edge_types,
                    drop_unusable=config.drop_unusable,
                ),
                cache,
                extractor,
                cwe_vocab=vocab,
                limit=limit,
            )
            rule_b_rows.extend(rule_b.rows)
        processed = root / "processed"
        reports = root / "reports"
        processed.mkdir(exist_ok=True)
        reports.mkdir(exist_ok=True)
        _atomic_save(processed / f"{split}.pt", built.data_list)
        try:
            import pyarrow as pa

            pq.write_table(pa.Table.from_pylist(built.rows), reports / f"{split}_rows.parquet")
        except (ImportError, pa.ArrowInvalid):
            (reports / f"{split}_rows.json").write_text(
                json.dumps(built.rows, default=str), encoding="utf-8"
            )
        from shield_core.graph_dataset.stats import edge_type_totals, size_summary

        summary[split] = {
            "input_rows": len(built.rows),
            "label_counts": {
                str(label): sum(row["label"] == label for row in built.rows) for label in (0, 1)
            },
            "ok": len(built.data_list),
            "statuses": {
                s: sum(r["status"] == s for r in built.rows)
                for s in sorted({r["status"] for r in built.rows})
            },
            "sizes": size_summary(built.rows),
            "edge_type_totals": edge_type_totals(built.rows),
            "usable_share": sum(bool(r.get("usable")) for r in built.rows)
            / max(1, len(built.rows)),
            "unseen_cwe_count": sum(len(r.get("unseen_cwe", [])) for r in built.rows),
        }
    (root / "cwe_vocab.json").write_text(json.dumps(vocab, indent=2), encoding="utf-8")
    (root / "config.json").write_text(
        json.dumps(
            {
                "converter_version": CONVERTER_VERSION,
                "graph_schema_version": "0.1-draft",
                "extractor": extractor.name,
                "extractor_version": extractor.version,
                "config": config.to_dict(),
                "cwe_vocab": vocab,
                "split_sha256": split_hashes,
                "build_date_utc": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (root / "build_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    from shield_core.graph_dataset.stats import cap_table, render_report

    ablation = None
    if config.stub_rule == "A":
        ablation = {
            "graphs_a": sum(r["status"] == "ok" for r in all_rows),
            "graphs_b": sum(r["status"] == "ok" for r in rule_b_rows),
            "nodes_a": sum(r["n_nodes"] for r in all_rows),
            "nodes_b": sum(r["n_nodes"] for r in rule_b_rows),
            "edges_a": sum(r["n_edges"] for r in all_rows),
            "edges_b": sum(r["n_edges"] for r in rule_b_rows),
        }
    report = render_report(
        language,
        config,
        summary,
        cap_table(all_rows, [250, 500, 750, 1000]),
        ablation,
    )
    (root / "pyg_dataset_report.md").write_text(report, encoding="utf-8")
    return root


def _atomic_save(path: Path, data_list: list) -> None:
    from torch_geometric.data import InMemoryDataset

    fd, temp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    os.close(fd)
    try:
        InMemoryDataset.save(data_list, temp)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)
