import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "data" / "interim" / "joern_spike_full"
RESULTS_FILE = ROOT / "data" / "interim" / "joern_spike_results.csv"
AUDIT_FILE = ROOT / "data" / "interim" / "joern_spike_audit.csv"
REPORT_FILE = ROOT / "docs" / "joern_spike.md"


def inspect_dot_file(path):
    """Count DOT nodes and edges within one graph file."""
    text = path.read_text(encoding="utf-8", errors="replace")

    nodes = set()
    edges = set()
    labels = {}

    for line in text.splitlines():
        edge_match = re.match(r'^\s*"([^"]+)"\s*->\s*"([^"]+)"', line)
        if edge_match:
            edges.add((edge_match.group(1), edge_match.group(2)))
            continue

        node_match = re.match(r'^\s*"([^"]+)"\s*\[label\s*=\s*<(.+)>', line)
        if node_match:
            node_id, label = node_match.groups()
            nodes.add(node_id)
            labels[node_id] = label

    unknown_nodes = sum("UNKNOWN" in label.upper() for label in labels.values())
    method_nodes = sum(re.search(r"\bMETHOD\b", label) is not None for label in labels.values())
    condition_nodes = sum(
        any(keyword in label.upper() for keyword in ("CONTROL_STRUCTURE", "CONDITION"))
        for label in labels.values()
    )

    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "unknown_nodes": unknown_nodes,
        "method_nodes": method_nodes,
        "condition_nodes": condition_nodes,
    }


def inspect_graph_directory(directory):
    files = sorted(directory.glob("*.dot")) if directory.exists() else []

    totals = {
        "dot_files": len(files),
        "nodes": 0,
        "edges": 0,
        "unknown_nodes": 0,
        "method_nodes": 0,
        "condition_nodes": 0,
        "nonempty_dot_files": 0,
    }

    for path in files:
        stats = inspect_dot_file(path)

        for key in (
            "nodes",
            "edges",
            "unknown_nodes",
            "method_nodes",
            "condition_nodes",
        ):
            totals[key] += stats[key]

        if stats["nodes"] > 0 or stats["edges"] > 0:
            totals["nonempty_dot_files"] += 1

    return totals


def main():
    if not RESULTS_FILE.exists():
        raise FileNotFoundError(f"Original results file not found: {RESULTS_FILE}")

    results = pd.read_csv(RESULTS_FILE)
    audit_rows = []

    for _, row in results.iterrows():
        language = str(row["language"])
        index = int(row["sample_index"])
        sample_name = f"{language}_{index:02d}"
        sample_dir = TEST_DIR / sample_name

        cpg_file = sample_dir / "cpg.bin"
        cfg = inspect_graph_directory(sample_dir / "cfg_export")
        ddg = inspect_graph_directory(sample_dir / "ddg_export")

        source_file = next(
            (p for p in sample_dir.glob("sample.*") if p.is_file()),
            None,
        )

        cpg_exists = cpg_file.is_file() and cpg_file.stat().st_size > 0
        source_exists = source_file is not None and source_file.stat().st_size > 0

        cfg_has_nodes = cfg["nodes"] > 0
        cfg_has_edges = cfg["edges"] > 0
        cfg_has_method = cfg["method_nodes"] > 0
        ddg_has_nodes = ddg["nodes"] > 0
        ddg_has_edges = ddg["edges"] > 0

        flags = []

        if not source_exists:
            flags.append("MISSING_SOURCE")
        if not cpg_exists:
            flags.append("MISSING_OR_EMPTY_CPG")
        if cfg["dot_files"] == 0:
            flags.append("NO_CFG_DOT_FILES")
        elif not cfg_has_nodes:
            flags.append("CFG_HAS_NO_NODES")
        if cfg_has_nodes and not cfg_has_edges:
            flags.append("CFG_HAS_NO_EDGES")
        if cfg_has_nodes and not cfg_has_method:
            flags.append("CFG_NO_METHOD_NODE")
        if cfg["unknown_nodes"]:
            flags.append("CFG_UNKNOWN_NODES")
        if ddg["dot_files"] == 0:
            flags.append("NO_DDG_DOT_FILES")
        elif not ddg_has_nodes:
            flags.append("DDG_HAS_NO_NODES")
        if ddg_has_nodes and not ddg_has_edges:
            flags.append("DDG_HAS_NO_EDGES")

        audit_rows.append(
            {
                "sample": sample_name,
                "language": language,
                "sample_index": index,
                "source_exists_nonempty": source_exists,
                "cpg_exists_nonempty": cpg_exists,
                "cpg_size_bytes": cpg_file.stat().st_size if cpg_exists else 0,
                "original_pipeline_success": row.get("pipeline_success"),
                "cfg_dot_files": cfg["dot_files"],
                "cfg_nonempty_dot_files": cfg["nonempty_dot_files"],
                "cfg_nodes_total_per_file": cfg["nodes"],
                "cfg_edges_total_per_file": cfg["edges"],
                "cfg_unknown_nodes": cfg["unknown_nodes"],
                "cfg_method_nodes": cfg["method_nodes"],
                "cfg_condition_nodes": cfg["condition_nodes"],
                "cfg_has_nodes": cfg_has_nodes,
                "cfg_has_edges": cfg_has_edges,
                "cfg_has_method_node": cfg_has_method,
                "ddg_dot_files": ddg["dot_files"],
                "ddg_nonempty_dot_files": ddg["nonempty_dot_files"],
                "ddg_nodes_total_per_file": ddg["nodes"],
                "ddg_edges_total_per_file": ddg["edges"],
                "ddg_has_nodes": ddg_has_nodes,
                "ddg_has_edges": ddg_has_edges,
                "review_flags": ";".join(flags),
            }
        )

    audit = pd.DataFrame(audit_rows)
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(AUDIT_FILE, index=False)

    report_lines = [
        "# Joern Spike Audit Report",
        "",
        "## Scope",
        "",
        "Audit of the existing Joern spike artifacts for up to 60 samples.",
        "This script does not rerun Joern or modify the original results.",
        "",
        "DOT node and edge counts are summed per file. Node IDs may repeat",
        "between files, so these totals are not guaranteed to be globally unique.",
        "A METHOD node alone does not prove that a useful method-level graph exists.",
        "DDG node/edge presence does not prove semantic data-dependence correctness.",
        "CALL resolution and source-to-graph semantic correctness were not verified.",
        "",
        "## Results by language",
        "",
    ]

    for language, group in audit.groupby("language"):
        report_lines.extend(
            [
                f"### {language}",
                "",
                f"- Samples audited: {len(group)}",
                f"- Nonempty CPGs: {int(group['cpg_exists_nonempty'].sum())}",
                f"- Samples with CFG nodes: {int(group['cfg_has_nodes'].sum())}",
                f"- Samples with CFG edges: {int(group['cfg_has_edges'].sum())}",
                f"- Samples with a METHOD node: {int(group['cfg_has_method_node'].sum())}",
                f"- Samples with DDG nodes: {int(group['ddg_has_nodes'].sum())}",
                f"- Samples with DDG edges: {int(group['ddg_has_edges'].sum())}",
                f"- Samples flagged for review: {int(group['review_flags'].ne('').sum())}",
                "",
            ]
        )

    report_lines.extend(
        [
            "## Interpretation and limitations",
            "",
            "- Export success is not equivalent to graph usability.",
            "- Empty DDGs are flagged for review; whether this is expected depends on the source.",
            "- UNKNOWN nodes and missing method nodes are diagnostic indicators, "
            "not automatic proof of failure.",
            "- Condition-node counts are simple label-based indicators, not semantic validation.",
            "- CALL resolution was not measured.",
            "- GO/NO-GO decisions require agreed acceptance thresholds and "
            "representative manual validation.",
            "",
            "## Artifacts",
            "",
            f"- Audit CSV: `{AUDIT_FILE.relative_to(ROOT).as_posix()}`",
            f"- Original results CSV: `{RESULTS_FILE.relative_to(ROOT).as_posix()}`",
        ]
    )

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    print(f"Audit saved: {AUDIT_FILE}")
    print(f"Report saved: {REPORT_FILE}")
    print("\nSummary by language:")
    print(
        audit.groupby("language")
        .agg(
            samples=("sample", "count"),
            cpg_ok=("cpg_exists_nonempty", "sum"),
            cfg_with_nodes=("cfg_has_nodes", "sum"),
            cfg_with_edges=("cfg_has_edges", "sum"),
            cfg_with_method=("cfg_has_method_node", "sum"),
            ddg_with_nodes=("ddg_has_nodes", "sum"),
            ddg_with_edges=("ddg_has_edges", "sum"),
            flagged=("review_flags", lambda s: s.ne("").sum()),
        )
        .to_string()
    )


if __name__ == "__main__":
    main()
