"""Probe file attribution and compare batched Joern exports with per-file extraction.

Run with ``python -m scripts.spikes.joern.benchmark_fidelity``. The script writes a JSON
artifact under ``data/interim/joern_benchmark`` and updates the benchmark report via its
normal generator. Docker job folders are kept outside OneDrive in the system temp directory.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

from scripts.spikes.joern.benchmark_core import BENCH_GROUPS, Sample
from scripts.spikes.joern.benchmark_extraction import _find_export, run_variant_c
from scripts.spikes.joern.benchmark_samples import load_spike_samples
from shield_core.extraction.joern_extractor import JoernExtractor
from shield_core.paths import BENCHMARK_DIR, REPO_ROOT

GRAPHML = "{http://graphml.graphdrawing.org/xmlns}"
IGNORED_NODE_TYPES = {"METHOD_PARAMETER_IN", "METHOD_PARAMETER_OUT"}


def _graphml(source: Path | str) -> tuple[dict[str, dict[str, str]], list[dict[str, Any]]]:
    root = (
        ET.fromstring(source)
        if isinstance(source, str) and source.lstrip().startswith("<")
        else ET.parse(source).getroot()
    )
    names = {key.get("id"): key.get("attr.name") for key in root.iter(f"{GRAPHML}key")}

    def attrs(element: ET.Element) -> dict[str, str]:
        return {
            names.get(data.get("key"), data.get("key")) or "": data.text or ""
            for data in element.iter(f"{GRAPHML}data")
        }

    nodes = {node.get("id", ""): attrs(node) for node in root.iter(f"{GRAPHML}node")}
    edges = [
        {
            "source": edge.get("source", ""),
            "target": edge.get("target", ""),
            **attrs(edge),
        }
        for edge in root.iter(f"{GRAPHML}edge")
    ]
    return nodes, edges


def _file_key(value: str, file_keys: set[str]) -> str | None:
    normalized = value.replace("\\", "/").strip().strip("<>")
    base = normalized.rsplit("/", 1)[-1]
    stem = Path(base).stem
    return next((key for key in file_keys if base == key or stem == Path(key).stem), None)


def attribute_nodes(
    nodes: dict[str, dict[str, str]],
    edges: list[dict[str, Any]],
    file_keys: set[str] | None = None,
) -> dict[str, str]:
    """Assign nodes by Joern filename signals or file-node AST/CONTAINS reachability.

    Nodes with no unique source-file attribution are deliberately omitted (unattributable
    shared stubs). Conflicting signals also remain unattributable rather than being guessed.
    """
    if file_keys is None:
        file_keys = set()
        for data in nodes.values():
            value = data.get("FILENAME", "")
            if not value and data.get("labelV") in {"FILE", "SOURCE_FILE"}:
                value = data.get("NAME", "")
            if value and value not in {"<empty>", "<unknown>"}:
                file_keys.add(Path(value.replace("\\", "/").rsplit("/", 1)[-1]).name)
    owners: dict[str, set[str]] = defaultdict(set)
    file_nodes: dict[str, set[str]] = defaultdict(set)
    for node_id, data in nodes.items():
        for signal in ("FILENAME", "NAME"):
            candidate = _file_key(data.get(signal, ""), file_keys)
            if candidate and (
                signal == "FILENAME" or data.get("labelV") in {"FILE", "SOURCE_FILE"}
            ):
                owners[node_id].add(candidate)
        if data.get("labelV") in {"FILE", "SOURCE_FILE"}:
            candidate = _file_key(data.get("NAME", "") or data.get("FILENAME", ""), file_keys)
            if candidate:
                file_nodes[candidate].add(node_id)

    adjacency: dict[str, set[str]] = defaultdict(set)
    source_adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge.get("labelE") in {"AST", "CONTAINS"}:
            src, dst = edge["source"], edge["target"]
            adjacency[src].add(dst)
        elif edge.get("labelE") == "SOURCE_FILE":
            src, dst = edge["source"], edge["target"]
            source_adjacency[src].add(dst)
            source_adjacency[dst].add(src)

    # SOURCE_FILE edges explicitly associate CPG nodes with FILE/SOURCE_FILE nodes.
    for key, starts in file_nodes.items():
        visited = set(starts)
        queue = deque(starts)
        while queue:
            current = queue.popleft()
            for neighbor in source_adjacency[current] - visited:
                visited.add(neighbor)
                queue.append(neighbor)
        for node_id in visited:
            owners[node_id].add(key)

    # Joern's filename attributes are sparse: methods/namespace/type nodes carry the
    # source path while their AST children often do not. Propagate only down AST edges.
    queue = deque(
        node_id
        for node_id, keys in owners.items()
        if len(keys) == 1 and nodes.get(node_id, {}).get("labelV") not in {"FILE", "SOURCE_FILE"}
    )
    while queue:
        current = queue.popleft()
        key = next(iter(owners[current]))
        for child in adjacency[current]:
            if owners.get(child) and owners[child] != {key}:
                continue
            if not owners.get(child):
                owners[child].add(key)
                queue.append(child)
    return {node_id: next(iter(keys)) for node_id, keys in owners.items() if len(keys) == 1}


def signal_diagnostics(
    nodes: dict[str, dict[str, str]], edges: list[dict[str, Any]], file_keys: set[str]
) -> dict[str, dict[str, Any]]:
    diagnostics: dict[str, dict[str, Any]] = {}
    for signal in (
        "METHOD.FILENAME",
        "NAMESPACE_BLOCK.FILENAME",
        "TYPE_DECL.FILENAME",
        "FILE.NAME",
    ):
        label, attribute = signal.split(".")
        by_file: Counter[str] = Counter()
        for data in nodes.values():
            if data.get("labelV") == label:
                key = _file_key(data.get(attribute, ""), file_keys)
                if key:
                    by_file[key] += 1
        diagnostics[signal] = {"files": sorted(by_file), "counts": dict(by_file)}

    source_file_nodes = {
        node_id
        for node_id, data in nodes.items()
        if data.get("labelV") in {"SOURCE_FILE", "FILE"}
        and _file_key(data.get("NAME", "") or data.get("FILENAME", ""), file_keys)
    }
    source_edges = [edge for edge in edges if edge.get("labelE") == "SOURCE_FILE"]
    diagnostics["SOURCE_FILE edges"] = {
        "files": sorted(
            {
                key
                for edge in source_edges
                for node_id in (edge["source"], edge["target"])
                if node_id in source_file_nodes
                for key in [
                    _file_key(
                        nodes[node_id].get("NAME", "") or nodes[node_id].get("FILENAME", ""),
                        file_keys,
                    )
                ]
                if key
            }
        ),
        "count": len(source_edges),
    }
    owners = attribute_nodes(nodes, edges, file_keys)
    methods = {node_id for node_id, data in nodes.items() if data.get("labelV") == "METHOD"}
    diagnostics["AST/CONTAINS reachability from file nodes"] = {
        "method_coverage": f"{sum(node_id in owners for node_id in methods)}/{len(methods)}",
        "files": sorted({owners[node_id] for node_id in methods if node_id in owners}),
    }
    return diagnostics


def _histograms(
    nodes: dict[str, dict[str, str]], edges: list[dict[str, Any]], owners: dict[str, str]
) -> tuple[Counter[str], Counter[str]]:
    node_types = Counter(
        data.get("labelV", "")
        for node_id, data in nodes.items()
        if node_id in owners and data.get("labelV") not in IGNORED_NODE_TYPES
    )
    edge_types = Counter(
        edge.get("labelE", "")
        for edge in edges
        if edge["source"] in owners
        and edge["target"] in owners
        and owners[edge["source"]] == owners[edge["target"]]
    )
    return node_types, edge_types


def compare_graphs(
    batch_nodes: dict[str, dict[str, str]],
    batch_edges: list[dict[str, Any]],
    batch_owners: dict[str, str],
    singles: dict[str, tuple[list[Any], list[Any]]],
    keys: set[str],
) -> dict[str, Any]:
    batched_nodes, batched_edges = _histograms(batch_nodes, batch_edges, batch_owners)
    cross_file_calls = sum(
        edge.get("labelE") == "CALL"
        and edge["source"] in batch_owners
        and edge["target"] in batch_owners
        and batch_owners[edge["source"]] != batch_owners[edge["target"]]
        for edge in batch_edges
    )
    per_file: dict[str, Any] = {}
    for key in sorted(keys):
        reference_nodes, reference_edges = singles[key]
        expected_nodes = Counter(
            node.type for node in reference_nodes if node.type not in IGNORED_NODE_TYPES
        )
        expected_edges = Counter(edge.type for edge in reference_edges)
        got_nodes = Counter(
            batch_nodes[node_id].get("labelV", "")
            for node_id, owner in batch_owners.items()
            if owner == key and batch_nodes[node_id].get("labelV") not in IGNORED_NODE_TYPES
        )
        got_edges = Counter(
            edge.get("labelE", "")
            for edge in batch_edges
            if edge["source"] in batch_owners
            and edge["target"] in batch_owners
            and batch_owners[edge["source"]] == key
            and batch_owners[edge["target"]] == key
        )
        node_delta = sum((expected_nodes - got_nodes).values()) + sum(
            (got_nodes - expected_nodes).values()
        )
        edge_delta = sum((expected_edges - got_edges).values()) + sum(
            (got_edges - expected_edges).values()
        )
        total = sum(expected_nodes.values()) + sum(expected_edges.values())
        per_file[key] = {
            "node_types_match": expected_nodes == got_nodes,
            "edge_types_match": expected_edges == got_edges,
            "expected_nodes": sum(expected_nodes.values()),
            "attributed_nodes": sum(got_nodes.values()),
            "expected_edges": sum(expected_edges.values()),
            "attributed_edges": sum(got_edges.values()),
            "mismatch_rate": (node_delta + edge_delta) / max(total, 1),
        }
    method_nodes = {
        node_id for node_id, data in batch_nodes.items() if data.get("labelV") == "METHOD"
    }
    unattributable_methods = sorted(method_nodes - batch_owners.keys())
    ignored_types = Counter(
        data.get("labelV", "")
        for node_id, data in batch_nodes.items()
        if node_id not in batch_owners
    )
    return {
        "per_file": per_file,
        "unattributable_method_nodes": len(unattributable_methods),
        "ignored_node_types": sorted(set(ignored_types) | IGNORED_NODE_TYPES),
        "ignored_node_type_counts": dict(ignored_types),
        "cross_file_call_edges": cross_file_calls,
        "match_rule": (
            "exact per-file node-type and edge-type histograms; omit unattributable nodes and "
            "their incident edges, plus METHOD_PARAMETER_IN/OUT"
        ),
        "batch_attributable_nodes": sum(owner in keys for owner in batch_owners.values()),
        "batch_total_nodes": len(batch_nodes),
        "batch_attributable_edges": sum(
            edge["source"] in batch_owners and edge["target"] in batch_owners
            for edge in batch_edges
        ),
    }


def _verdict(comparison: dict[str, Any]) -> tuple[str, list[str]]:
    files = comparison["per_file"].values()
    if not comparison["unattributable_method_nodes"] and all(
        row["node_types_match"] and row["edge_types_match"] for row in files
    ):
        return "usable", []
    reasons = []
    if comparison["unattributable_method_nodes"]:
        reasons.append(
            f"{comparison['unattributable_method_nodes']} METHOD nodes lack unique file attribution"
        )
    mismatched = [
        name
        for name, row in comparison["per_file"].items()
        if not row["node_types_match"] or not row["edge_types_match"]
    ]
    if mismatched:
        reasons.append("per-file type histograms differ for " + ", ".join(mismatched))
    return "usable with caveats" if not comparison[
        "unattributable_method_nodes"
    ] else "not usable", reasons


def _samples() -> dict[str, list[Sample]]:
    spike = load_spike_samples()
    selected = {
        group: [sample for sample in spike if sample.group == group][:2]
        for group in BENCH_GROUPS
        if group != "python"
    }
    fixture_dir = REPO_ROOT / "tests" / "fixtures" / "joern"
    selected["python"] = [
        Sample(
            f"python_fidelity_{name[:-3]}",
            "python",
            ".py",
            (fixture_dir / name).read_text(encoding="utf-8"),
            "fidelity",
            "fixture",
            index,
        )
        for index, name in enumerate(("calls.py", "get_user.py"))
    ]
    return selected


def run_probe(
    *, image: str = "shield-joern", xmx: str = "4g", timeout: int = 300
) -> dict[str, Any]:
    all_samples = _samples()
    root = Path(tempfile.gettempdir()) / "shield_bench_fidelity"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    extractor = JoernExtractor(docker_image=image, timeout=timeout)
    report: dict[str, Any] = {"groups": {}, "joern_image": image}
    try:
        for group, samples in all_samples.items():
            run_id = f"fidelity-{group}"
            outcome = run_variant_c(
                samples,
                image=image,
                xmx=xmx,
                timeout=timeout,
                batch_size=2,
                work_dir=root,
                run_id=run_id,
                keep=True,
            )
            if any(not sample.ok for sample in outcome.results):
                raise RuntimeError(f"batched {group} extraction failed: {outcome.results}")
            export = _find_export(root / run_id, 1)
            if export is None:
                raise RuntimeError(f"missing combined GraphML for {group}")
            nodes, edges = _graphml(export)
            keys = {f"{sample.sample_id}{sample.extension}" for sample in samples}
            owners = attribute_nodes(nodes, edges, keys)
            singles = {}
            for sample in samples:
                graph = extractor.extract(
                    sample.code, BENCH_GROUPS[group][0], extension=sample.extension
                )
                singles[f"{sample.sample_id}{sample.extension}"] = (graph.nodes, graph.edges)
            comparison = compare_graphs(nodes, edges, owners, singles, keys)
            verdict, caveats = _verdict(comparison)
            report["groups"][group] = {
                "sample_ids": [sample.sample_id for sample in samples],
                "candidate_signals": signal_diagnostics(nodes, edges, keys),
                **comparison,
                "verdict": verdict,
                "caveats": caveats,
                "follow_up": (
                    "Test distinct Joern wrappers per file or variant D: one JVM with one "
                    "importCode per file."
                    if group == "python" and verdict == "not usable"
                    else None
                ),
            }
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return report


def main() -> None:
    result = run_probe()
    output = BENCHMARK_DIR / "fidelity.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"written: {output}")


if __name__ == "__main__":
    main()
