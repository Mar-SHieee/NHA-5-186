"""Extract, analyze, and report Joern graph-quality triage results."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from scripts.spikes.joern.benchmark_core import BENCH_GROUPS, Sample
from scripts.spikes.joern.benchmark_samples import draw_scale_samples, load_spike_samples
from scripts.spikes.joern.triage_core import (
    DotStats,
    audit_flags,
    classify,
    flow_expectation,
    graph_metrics,
    is_usable,
    language_verdict,
    parse_dot,
    stub_rule_impact,
    substring_unknown_count,
    wilson_interval,
)
from shield_core.extraction.cache import CachedGraphExtractor, CacheKey, GraphCache
from shield_core.extraction.graph_extractor import CodeGraph
from shield_core.extraction.joern_extractor import JoernExtractor
from shield_core.paths import DOCS_GRAPHS_DIR, INTERIM_DIR, JOERN_TRIAGE_DIR

SPIKE_DIR = INTERIM_DIR / "joern_spike_full"
GRAPH_CACHE_DIR = JOERN_TRIAGE_DIR / "graph_cache"
REVIEW_CSV = DOCS_GRAPHS_DIR / "joern_triage_review.csv"
REPORT_PATH = DOCS_GRAPHS_DIR / "joern_triage.md"
TRIAGE_COLUMNS = [
    "sample_id",
    "language",
    "spike_dir",
    "flagged",
    "review_flags",
    "ddg_dot_edges",
    "cfg_dot_edges",
    "n_nodes",
    "n_edges",
    "reaching_def",
    "cfg_edges",
    "call_edges",
    "n_unknown_nodes",
    "unknown_share",
    "substring_unknown",
    "real_methods",
    "lineless_methods",
    "expected_flow",
    "flow_method",
    "auto_cause",
    "auto_reason",
    "usable",
]
REVIEW_COLUMNS = [
    "sample_id",
    "language",
    "auto_cause",
    "human_cause",
    "agrees",
    "evidence",
]
CAUSES_REQUIRING_REVIEW = {"PARSER_GAP", "INPUT_FRAGMENT", "EXTRACTION_FAILURE", "OTHER"}


def _sample_spike_dir(sample: Sample, spike_root: Path) -> Path:
    """Map benchmark ids back to the original run's language_01 directory names."""
    index = int(sample.sample_id.rsplit("_", maxsplit=1)[-1])
    return spike_root / f"{sample.group}_{index:02d}"


def _dot_directory(directory: Path) -> DotStats:
    """Aggregate per-method DOT files while namespacing IDs that repeat between methods."""
    files = sorted(directory.glob("*.dot")) if directory.is_dir() else []
    nodes: dict[str, str] = {}
    edges: set[tuple[str, str]] = set()
    for path in files:
        stats = parse_dot(path.read_text(encoding="utf-8", errors="replace"))
        nodes.update({f"{path.name}:{node_id}": label for node_id, label in stats.nodes.items()})
        edges.update((f"{path.name}:{src}", f"{path.name}:{dst}") for src, dst in stats.edges)
    return DotStats(nodes=nodes, edges=edges, dot_files=len(files))


def _unbalanced_braces(code: str) -> bool:
    """Spot obviously incomplete C/C++ snippets without treating braces in text as syntax."""
    cleaned = re.sub(
        r"/\*.*?\*/|//[^\n]*|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'", " ", code, flags=re.S
    )
    depth = 0
    for char in cleaned:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return True
    return depth != 0


def _samples_for_set(sample_set: str, group: str | None, n: int, seed: int) -> list[Sample]:
    """Load the frozen spike set or a deterministic scale sample with spike rows excluded."""
    if sample_set == "spike":
        samples = load_spike_samples()
    else:
        excluded = {sample.sha256 for sample in load_spike_samples()}
        samples = draw_scale_samples(n_per_group=n, seed=seed, exclude_sha=excluded)
    return [sample for sample in samples if group is None or sample.group == group]


def extract_samples(
    *, sample_set: str = "spike", group: str | None = None, n: int = 100, seed: int = 43
) -> tuple[int, int]:
    """Fill the selected graph-cache set, continuing past individual extraction failures."""
    samples = _samples_for_set(sample_set, group, n, seed)
    cache = GraphCache(GRAPH_CACHE_DIR)
    extractor = CachedGraphExtractor(JoernExtractor(docker_image="shield-joern"), cache)
    failures = 0
    for index, sample in enumerate(samples, start=1):
        language, extension = BENCH_GROUPS[sample.group]
        try:
            graph = extractor.extract(sample.code, language, extension)
            print(f"[{index}/{len(samples)}] {sample.sample_id}: {len(graph.nodes)} nodes")
        except Exception as exc:  # report extraction failures without aborting the batch
            failures += 1
            print(
                f"[{index}/{len(samples)}] {sample.sample_id}: FAILED {type(exc).__name__}: {exc}"
            )
    print(
        f"samples={len(samples)} failures={failures} "
        f"cache_hits={cache.hits} cache_misses={cache.misses}"
    )
    return len(samples), failures


def _review_card(
    sample: Sample,
    row: dict[str, Any],
    graph: CodeGraph,
    source: str,
    cfg_stats: DotStats,
    sample_set: str,
) -> str:
    """Build a self-contained text card so manual review does not require Joern or Docker."""
    node_by_id = {node.id: node for node in graph.nodes}
    lines = [
        f"# Review card: {sample.sample_id}",
        "",
        f"- Language group: `{sample.group}`",
        f"- Auto cause: `{row['auto_cause']}` — {row['auto_reason']}",
        f"- Flags: `{row['review_flags'] or '(none)'}`",
        f"- Expected flow: {row['expected_flow']} ({row['flow_method']})",
        f"- Usable by U1–U4: {row['usable']}",
        "",
        "## Metrics",
        "",
        f"Nodes: {row['n_nodes']} · Edges: {row['n_edges']} · "
        f"REACHING_DEF: {row['reaching_def']} · CFG: {row['cfg_edges']} · "
        f"CALL: {row['call_edges']} · UNKNOWN: {row['n_unknown_nodes']} "
        f"({row['unknown_share']:.1%})",
        f"METHODs: {row['real_methods']} line-numbered real, {row['lineless_methods']} line-less",
        f"Spike CFG edges: {row['cfg_dot_edges']} · DDG edges: {row['ddg_dot_edges']}",
        "",
        "## Source",
        "",
        "```text",
        *[f"{index:4d}: {line}" for index, line in enumerate(source.splitlines(), start=1)],
        "```",
        "",
        "## METHOD nodes (name, line)",
        "",
    ]
    methods = [node for node in graph.nodes if node.type == "METHOD"]
    lines.extend(f"- `{node.name}`, line `{node.line}`" for node in methods)
    if not methods:
        lines.append("- (none)")
    lines.extend(["", "## First 15 REACHING_DEF edges", ""])
    reaching = [edge for edge in graph.edges if edge.type == "REACHING_DEF"][:15]
    lines.extend(
        f"- `{node_by_id.get(edge.src).code}` → `{node_by_id.get(edge.dst).code}`"
        if edge.src in node_by_id and edge.dst in node_by_id
        else f"- node `{edge.src}` → node `{edge.dst}`"
        for edge in reaching
    )
    if not reaching:
        lines.append("- (none)")
    lines.extend(["", "## First 10 UNKNOWN nodes", ""])
    unknowns = [node for node in graph.nodes if node.type == "UNKNOWN"][:10]
    lines.extend(f"- line `{node.line}`: `{node.code}`" for node in unknowns)
    if not unknowns:
        lines.append("- (none)")
    if sample_set == "spike":
        lines.extend(["", "## CFG DOT labels containing UNKNOWN", ""])
        hits = [label for label in cfg_stats.nodes.values() if "UNKNOWN" in label.upper()][:10]
        lines.extend(f"- `{label}`" for label in hits) if hits else lines.append("- (none)")
    return "\n".join(lines) + "\n"


def _language_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate sample counts and uncertainty without hiding the small denominator."""
    usable = sum(bool(row["usable"]) for row in rows)
    n = len(rows)
    causes = Counter(row["auto_cause"] for row in rows)
    flags = Counter(flag for row in rows for flag in str(row["review_flags"]).split(";") if flag)
    low, high = wilson_interval(usable, n) if n else (None, None)
    return {
        "samples": n,
        "usable": usable,
        "wilson_interval": [low, high],
        "verdict": language_verdict(usable, n) if n else "NO DATA",
        "cause_counts": dict(sorted(causes.items())),
        "flag_counts": dict(sorted(flags.items())),
    }


def _stub_summary(graphs: list[tuple[str, str, CodeGraph]]) -> dict[str, Any]:
    """Aggregate Rule A/B evidence and keep per-sample component changes inspectable."""
    per_sample: dict[str, dict[str, Any]] = {}
    by_language: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[tuple[str, CodeGraph]]] = defaultdict(list)
    for sample_id, language, graph in graphs:
        grouped[language].append((sample_id, graph))
        impact = stub_rule_impact(graph)
        per_sample[sample_id] = {
            "dropped_nodes": impact.dropped_nodes,
            "dropped_edges_by_type": impact.dropped_edges_by_type,
            "kept_edge_loss": impact.kept_edge_loss,
            "components_a": impact.components_a,
            "components_b": impact.components_b,
            "dropped_have_text": impact.dropped_have_text,
        }

    for language, samples in grouped.items():
        edge_totals: Counter[str] = Counter()
        wrappers: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        lineless = 0
        for sample_id, graph in samples:
            metrics = graph_metrics(graph)
            lineless += metrics.n_lineless_methods
            impact = per_sample[sample_id]
            edge_totals.update(impact["dropped_edges_by_type"])
            for name, line in metrics.methods:
                if name in {"<module>", "<global>"}:
                    wrappers[name][str(line)] += 1
        by_language[language] = {
            "samples": len(samples),
            "lineless_methods": lineless,
            "dropped_edges_by_type": dict(sorted(edge_totals.items())),
            "kept_edge_loss": sum(
                v["kept_edge_loss"]
                for sid, v in per_sample.items()
                if sid in {s[0] for s in samples}
            ),
            "components_b_gt_a": [
                sid
                for sid, _ in samples
                if per_sample[sid]["components_b"] > per_sample[sid]["components_a"]
            ],
            "dropped_methods_with_text": [
                sid for sid, _ in samples if per_sample[sid]["dropped_have_text"]
            ],
            "wrapper_method_lines": {name: dict(lines) for name, lines in wrappers.items()},
        }
    return {"by_language": by_language, "samples": per_sample}


def analyze_samples(
    *,
    spike_root: Path = SPIKE_DIR,
    cache_root: Path = GRAPH_CACHE_DIR,
    output_dir: Path = JOERN_TRIAGE_DIR,
    sample_set: str = "spike",
    group: str | None = None,
    n: int = 100,
    seed: int = 43,
) -> dict[str, Any]:
    """Analyze cached graphs and spike views, writing the fixed CSV, JSON, and review cards."""
    samples = _samples_for_set(sample_set, group, n, seed)
    cache = GraphCache(cache_root)
    extractor = JoernExtractor(docker_image="shield-joern")
    output_dir = Path(output_dir)
    cards_dir = output_dir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    graphs: list[tuple[str, str, CodeGraph]] = []

    for sample in samples:
        language, extension = BENCH_GROUPS[sample.group]
        key = CacheKey.for_code(sample.code, language, extractor, extension)
        graph = cache.get(key)
        if graph is None:
            raise FileNotFoundError(
                f"No cached production graph for {sample.sample_id}; "
                "run the extract subcommand first."
            )
        metrics = graph_metrics(graph)
        if sample_set == "spike":
            sample_dir = _sample_spike_dir(sample, Path(spike_root))
            source_path = sample_dir / f"sample{extension}"
            source_ok = source_path.is_file() and source_path.stat().st_size > 0
            source = (
                source_path.read_text(encoding="utf-8", errors="replace")
                if source_ok
                else sample.code
            )
            cpg_path = sample_dir / "cpg.bin"
            cpg_ok = cpg_path.is_file() and cpg_path.stat().st_size > 0
            cfg_stats = _dot_directory(sample_dir / "cfg_export")
            ddg_stats = _dot_directory(sample_dir / "ddg_export")
            flags = audit_flags(cfg_stats, ddg_stats, cpg_ok=cpg_ok, source_ok=source_ok)
            ddg_edges = len(ddg_stats.edges)
            cfg_edges = len(cfg_stats.edges)
            substring_unknown = substring_unknown_count(cfg_stats.nodes.values())
            spike_view_available = True
            spike_dir_name = sample_dir.name
        else:
            source = sample.code
            flags = []
            cfg_stats = DotStats()
            ddg_stats = DotStats()
            ddg_edges = 0
            cfg_edges = 0
            substring_unknown = 0
            spike_view_available = False
            spike_dir_name = ""

        expected_flow, flow_method = flow_expectation(language, sample.code)
        row_for_rules: dict[str, Any] = {
            "real_methods": metrics.n_real_methods,
            "cfg_edges": metrics.edge_counts.get("CFG", 0),
            "expected_flow": expected_flow,
            "reaching_def": metrics.edge_counts.get("REACHING_DEF", 0),
            "unknown_share": metrics.unknown_share,
            "ddg_dot_edges": ddg_edges,
            "spike_view_available": spike_view_available,
            "flagged": bool(flags),
            "review_flags": ";".join(flags),
            "input_fragment": metrics.n_real_methods == 0,
            "unbalanced_braces": (sample.group in {"c", "cpp"} and _unbalanced_braces(sample.code)),
        }
        auto_cause, auto_reason = classify(row_for_rules)
        usable = is_usable(row_for_rules)
        row: dict[str, Any] = {
            "sample_id": sample.sample_id,
            "language": sample.group,
            "spike_dir": spike_dir_name,
            "flagged": bool(flags),
            "review_flags": ";".join(flags),
            "ddg_dot_edges": ddg_edges,
            "cfg_dot_edges": cfg_edges,
            "n_nodes": metrics.n_nodes,
            "n_edges": metrics.n_edges,
            "reaching_def": metrics.edge_counts.get("REACHING_DEF", 0),
            "cfg_edges": metrics.edge_counts.get("CFG", 0),
            "call_edges": metrics.edge_counts.get("CALL", 0),
            "n_unknown_nodes": metrics.n_unknown_nodes,
            "unknown_share": metrics.unknown_share,
            "substring_unknown": substring_unknown,
            "real_methods": metrics.n_real_methods,
            "lineless_methods": metrics.n_lineless_methods,
            "expected_flow": expected_flow,
            "flow_method": flow_method,
            "auto_cause": auto_cause,
            "auto_reason": auto_reason,
            "usable": usable,
        }
        rows.append(row)
        graphs.append((sample.sample_id, sample.group, graph))

        needs_review = (sample_set == "spike" and (bool(flags) or not ddg_stats.nodes)) or (
            sample_set != "spike" and (not usable or auto_cause in CAUSES_REQUIRING_REVIEW)
        )
        if needs_review:
            card = _review_card(sample, row, graph, source, cfg_stats, sample_set)
            (cards_dir / f"{sample.sample_id}.md").write_text(card, encoding="utf-8")

    csv_path = output_dir / "triage.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRIAGE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    languages = {
        language: _language_summary([row for row in rows if row["language"] == language])
        for language in sorted({row["language"] for row in rows})
    }
    summary: dict[str, Any] = {
        "sample_set": sample_set,
        "group_filter": group,
        "sample_count": len(rows),
        "criteria": {
            "real_methods": "at least one line-numbered METHOD other than <module>/<global>",
            "cfg_edges": ">= 1",
            "reaching_def": "required only when expected_flow > 0",
            "unknown_share_max": 0.05,
            "go_rate": 0.85,
            "go_with_limits_rate": 0.70,
        },
        "languages": languages,
        "production_failure_count": 0,
        "stub_rule": _stub_summary(graphs),
        "audit_counts": {
            language: {
                "flagged": sum(bool(row["flagged"]) for row in rows if row["language"] == language),
                "empty_ddg": sum(
                    "DDG_HAS_NO_NODES" in str(row["review_flags"]).split(";")
                    and sample_set == "spike"
                    for row in rows
                    if row["language"] == language
                ),
            }
            for language in sorted({row["language"] for row in rows})
        },
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {csv_path}")
    print(f"Wrote {summary_path}")
    print(f"Review cards: {sum(path.is_file() for path in cards_dir.glob('*.md'))}")
    return summary


def _load_review_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _addendum(summary: dict[str, Any]) -> str:
    languages = summary.get("languages", {})
    verdicts = []
    for language in ("python", "c", "cpp"):
        result = languages.get(language)
        if result:
            interval = result.get("wilson_interval", [None, None])
            verdicts.append(
                f"{language}: **{result['verdict']}** ({result['usable']}/{result['samples']}; "
                f"95% Wilson {interval[0]:.2f}–{interval[1]:.2f})."
            )
    return "\n".join(
        [
            "<!-- TRIAGE:BEGIN -->",
            "## Graph-quality triage (W2-P2-04)",
            "",
            *verdicts,
            "",
            "Full evidence: `docs/graphs/joern_triage.md`.",
            "<!-- TRIAGE:END -->",
        ]
    )


def _report_text(
    rows: list[dict[str, str]],
    summary: dict[str, Any],
    review_rows: list[dict[str, str]],
    scale_summary: dict[str, Any] | None,
) -> str:
    lines = [
        "# Joern graph-quality triage",
        "",
        (
            "Generated by `python -m scripts.spikes.joern.triage_joern_spike report`; "
            "do not hand-edit."
        ),
        "",
        "## Frozen criteria",
        "",
        (
            "- A usable graph has a line-numbered real METHOD (not only `<module>`/`<global>`), "
            "at least one CFG edge, REACHING_DEF when expected flow is positive, and no more "
            "than 5% UNKNOWN nodes."
        ),
        (
            "- Verdict thresholds: GO at 85%+, GO-WITH-LIMITS from 70% to below 85%, "
            "and NO-GO below 70%."
        ),
        "",
        "## Verdicts",
        "",
        "| Language | Usable | 95% Wilson interval | Verdict |",
        "| --- | ---: | ---: | --- |",
    ]
    for language in ("python", "c", "cpp"):
        result = summary.get("languages", {}).get(language)
        if not result:
            continue
        low, high = result["wilson_interval"]
        lines.append(
            f"| {language} | {result['usable']}/{result['samples']} | "
            f"{low:.2f}–{high:.2f} | {result['verdict']} |"
        )
    if scale_summary and "c" in scale_summary.get("languages", {}):
        c = scale_summary["languages"]["c"]
        base = summary.get("languages", {}).get("c", {})
        total_n = c["samples"] + base.get("samples", 0)
        total_usable = c["usable"] + base.get("usable", 0)
        low, high = wilson_interval(total_usable, total_n)
        lines.extend(
            [
                "",
                f"C extended check: original {base.get('usable', 0)}/{base.get('samples', 0)}, "
                f"scale {c['usable']}/{c['samples']}, combined {total_usable}/{total_n} "
                f"(95% Wilson {low:.2f}–{high:.2f}, {language_verdict(total_usable, total_n)}).",
            ]
        )
    lines.extend(["", "## Automatic cause counts", ""])
    for language, result in sorted(summary.get("languages", {}).items()):
        counts = ", ".join(f"`{cause}` {count}" for cause, count in result["cause_counts"].items())
        lines.append(f"- **{language}:** {counts or 'no automatic causes'}")

    agreement = sum(row.get("human_cause") == row.get("auto_cause") for row in review_rows)
    lines.extend(
        [
            "",
            "## Manual review",
            "",
            f"Rows reviewed: {len(review_rows)}; auto/human agreement: "
            f"{agreement}/{len(review_rows)}"
            + (f" ({agreement / len(review_rows):.1%})." if review_rows else "."),
            "",
            "## Stub-rule evidence",
            "",
            (
                "| Language | Line-less METHODs | Kept-edge loss under B | "
                "Samples where components B > A | Dropped methods with text |"
            ),
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    stub_languages = summary.get("stub_rule", {}).get("by_language", {})
    for language, result in sorted(stub_languages.items()):
        lines.append(
            f"| {language} | {result['lineless_methods']} | {result['kept_edge_loss']} | "
            f"{len(result['components_b_gt_a'])} | {len(result['dropped_methods_with_text'])} |"
        )

    lines.extend(
        [
            "",
            "## Hypotheses and current evidence",
            "",
            (
                "- **H1 (empty DDG is only a view problem):** compare `ddg_dot_edges` with "
                "production `REACHING_DEF` in the sample table below."
            ),
            (
                "- **H2 (frontend flag changes the graph):** production-path metrics are listed "
                "per sample; DOT CFG/DDG totals are a different graph view, so counts are not "
                "directly equivalent."
            ),
            (
                "- **H3 (UNKNOWN substring flags are mostly artifacts):** compare "
                "`substring_unknown`, `n_unknown_nodes`, and the review flags per sample."
            ),
            (
                "- **H4 (some empty DDGs are expected):** see expected-flow estimate and manual "
                "cause; C/C++ estimates are approximate."
            ),
            "- **H5 (C/C++ inputs are fragments):** see manual causes and review-sheet evidence.",
            (
                "- **H6 (stub rule only matters for C/C++):** see per-language line-less METHOD "
                "and Rule A/B impact above."
            ),
            "",
            "## Per-sample results",
            "",
            (
                "| Sample | Language | Flags | DDG DOT edges | Nodes | REACHING_DEF | CFG | "
                "UNKNOWN | Expected flow | Auto cause | Usable |"
            ),
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['sample_id']} | {row['language']} | {row['review_flags'] or '—'} | "
            f"{row['ddg_dot_edges']} | {row['n_nodes']} | {row['reaching_def']} | "
            f"{row['cfg_edges']} | "
            f"{row['n_unknown_nodes']} ({float(row['unknown_share']):.1%}) | "
            f"{row['expected_flow']} ({row['flow_method']}) | "
            f"{row['auto_cause']} | {row['usable']} |"
        )
    lines.extend(
        [
            "",
            "## Limitations and reproduction",
            "",
            (
                "The original spike has 20 samples per language; its Wilson intervals are wide. "
                "C/C++ expected-flow estimates use a regex heuristic and manual review is "
                "authoritative. The 60 spike samples do not establish representativeness of the "
                "full datasets. Any added C scale sample is reported separately and combined "
                "with the original only as a clearly labeled extension."
            ),
            "",
            "```powershell",
            "python -m scripts.spikes.joern.triage_joern_spike extract",
            "python -m scripts.spikes.joern.triage_joern_spike analyze",
            "python -m scripts.spikes.joern.triage_joern_spike report",
            "```",
            "",
            f"Manual evidence sheet: `{REVIEW_CSV.relative_to(REVIEW_CSV.parents[2]).as_posix()}`",
        ]
    )
    return "\n".join(lines) + "\n"


def report(
    *,
    triage_csv: Path = JOERN_TRIAGE_DIR / "triage.csv",
    summary_json: Path = JOERN_TRIAGE_DIR / "summary.json",
    review_csv: Path = REVIEW_CSV,
    output_path: Path = REPORT_PATH,
) -> str:
    """Generate the checked report and print marker-protected addendum text for the spike report."""
    with Path(triage_csv).open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    summary = json.loads(Path(summary_json).read_text(encoding="utf-8"))
    reviews = _load_review_rows(Path(review_csv))
    scale_path = JOERN_TRIAGE_DIR / "c_scale" / "summary.json"
    scale_summary = (
        json.loads(scale_path.read_text(encoding="utf-8")) if scale_path.is_file() else None
    )
    text = _report_text(rows, summary, reviews, scale_summary)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    addendum = _addendum(summary)
    print(f"Wrote {output_path}")
    print("\nAddendum text for docs/graphs/joern_spike.md:\n")
    print(addendum)
    return text


def _output_dir(sample_set: str, group: str | None) -> Path:
    if sample_set == "spike":
        return JOERN_TRIAGE_DIR
    return JOERN_TRIAGE_DIR / f"{group or 'all'}_scale"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("extract", "analyze"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--sample-set", choices=("spike", "scale"), default="spike")
        sub.add_argument("--group", choices=("python", "c", "cpp"))
        sub.add_argument(
            "--n", type=int, default=100, help="Scale samples per group (default: 100)"
        )
        sub.add_argument("--seed", type=int, default=43)
        if name == "analyze":
            sub.add_argument("--spike-root", type=Path, default=SPIKE_DIR)
            sub.add_argument("--cache-root", type=Path, default=GRAPH_CACHE_DIR)
            sub.add_argument("--output-dir", type=Path)
    subparsers.add_parser("report")
    args = parser.parse_args(argv)

    if args.command == "extract":
        extract_samples(sample_set=args.sample_set, group=args.group, n=args.n, seed=args.seed)
    elif args.command == "analyze":
        analyze_samples(
            spike_root=args.spike_root,
            cache_root=args.cache_root,
            output_dir=args.output_dir or _output_dir(args.sample_set, args.group),
            sample_set=args.sample_set,
            group=args.group,
            n=args.n,
            seed=args.seed,
        )
    else:
        report()


if __name__ == "__main__":
    main()
