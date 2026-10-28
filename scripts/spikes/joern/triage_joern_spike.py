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
from scripts.spikes.joern.benchmark_samples import (
    draw_c_scale_samples,
    draw_scale_samples,
    load_spike_samples,
    wrap_indented_python_method_snippets,
)
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


def _samples_for_set(
    sample_set: str,
    group: str | None,
    n: int,
    seed: int,
) -> list[Sample]:
    """Load the frozen spike set or a deterministic scale sample with spike rows excluded."""
    if sample_set == "spike":
        samples = load_spike_samples()
    elif sample_set == "c-scale":
        excluded = {sample.sha256 for sample in load_spike_samples()}
        samples = draw_c_scale_samples(n=n, seed=seed, exclude_sha=excluded)
    else:
        excluded = {sample.sha256 for sample in load_spike_samples()}
        samples = draw_scale_samples(n_per_group=n, seed=seed, exclude_sha=excluded)
    return [sample for sample in samples if group is None or sample.group == group]


def _wrap_python_sample_if_method_missing(sample: Sample, graph: CodeGraph) -> Sample:
    """Repair only Python samples whose baseline CPG has no line-numbered real METHOD."""
    if sample.group != "python" or graph_metrics(graph).n_real_methods:
        return sample
    prepared = wrap_indented_python_method_snippets([sample])[0]
    return prepared if prepared.code != sample.code else sample


def extract_samples(
    *,
    sample_set: str = "spike",
    group: str | None = None,
    n: int = 100,
    seed: int = 43,
    python_context_wrap: bool = False,
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
            prepared = (
                _wrap_python_sample_if_method_missing(sample, graph)
                if python_context_wrap
                else sample
            )
            if prepared.code != sample.code:
                graph = extractor.extract(prepared.code, language, extension)
                note = " (synthetic class wrapper)"
            else:
                note = ""
            print(f"[{index}/{len(samples)}] {sample.sample_id}: {len(graph.nodes)} nodes{note}")
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
    causes = Counter(row["auto_cause"] for row in rows if row["auto_cause"])
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
    python_context_wrap: bool = False,
) -> dict[str, Any]:
    """Analyze cached graphs and spike views, writing the fixed CSV, JSON, and review cards."""
    samples = _samples_for_set(sample_set, group, n, seed)
    cache = GraphCache(cache_root)
    extractor = JoernExtractor(docker_image="shield-joern")
    output_dir = Path(output_dir)
    cards_dir = output_dir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    for old_card in cards_dir.glob("*.md"):
        old_card.unlink()
    rows: list[dict[str, Any]] = []
    graphs: list[tuple[str, str, CodeGraph]] = []
    wrapped_samples = 0

    for sample in samples:
        language, extension = BENCH_GROUPS[sample.group]
        key = CacheKey.for_code(sample.code, language, extractor, extension)
        graph = cache.get(key)
        if graph is None:
            raise FileNotFoundError(
                f"No cached production graph for {sample.sample_id}; "
                "run the extract subcommand first."
            )
        if python_context_wrap:
            prepared = _wrap_python_sample_if_method_missing(sample, graph)
            if prepared.code != sample.code:
                sample = prepared
                wrapped_samples += 1
                key = CacheKey.for_code(sample.code, language, extractor, extension)
                graph = cache.get(key)
                if graph is None:
                    raise FileNotFoundError(
                        f"No cached wrapped graph for {sample.sample_id}; run extract "
                        "with --python-context-wrap first."
                    )
        metrics = graph_metrics(graph)
        if sample_set == "spike" and not python_context_wrap:
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
        usable = is_usable(row_for_rules)
        if not spike_view_available and not flags and usable:
            auto_cause = ""
            auto_reason = "No spike audit flags; the production graph passes U1–U4."
        else:
            auto_cause, auto_reason = classify(row_for_rules)
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

        needs_review = (spike_view_available and (bool(flags) or not ddg_stats.nodes)) or (
            not spike_view_available and (not usable or auto_cause in CAUSES_REQUIRING_REVIEW)
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
        "python_context_wrap": {"enabled": python_context_wrap, "wrapped_samples": wrapped_samples},
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
    wrapper_result = summary.get("python_context_wrap_experiment")
    wrapper_line = (
        f"Python is NO-GO on the current raw production path. The triage-only "
        f"synthetic-class experiment reached {wrapper_result['usable']}/"
        f"{wrapper_result['samples']} usable but needs source-line mapping "
        "validation before adoption. Recommendation: apply the wrapper consistently to "
        "indented Python method excerpts in production, with line-offset correction."
        if wrapper_result
        else "Python is NO-GO on the current raw production path."
    )
    verdicts = []
    for language in ("python", "c", "cpp"):
        result = languages.get(language)
        if result:
            interval = result.get("wilson_interval", [None, None])
            verdicts.append(
                f"{language}: **{result['verdict']}** ({result['usable']}/{result['samples']}; "
                f"95% Wilson {interval[0]:.2f}-{interval[1]:.2f})."
            )
    return "\n".join(
        [
            "<!-- TRIAGE:BEGIN -->",
            "## Graph-quality triage (W2-P2-04)",
            "",
            *verdicts,
            "",
            wrapper_line,
            "Main causes: Python input-context fragments; verified-C input fragments; "
            "C++ input fragments and expected no-flow cases.",
            "First-build stub rule: Rule A (provisional; revisit in the Week-3 ablation).",
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
    python_wrapped_summaries: dict[str, dict[str, Any]] | None = None,
    python_scale_summary: dict[str, Any] | None = None,
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
        if language == "c":
            # The original C-labelled spike is BigVul data whose metadata says cpp.
            continue
        if language == "python" and python_scale_summary:
            scale_python = python_scale_summary.get("languages", {}).get("python", {})
            n = result["samples"] + scale_python.get("samples", 0)
            usable = result["usable"] + scale_python.get("usable", 0)
            result = {
                "samples": n,
                "usable": usable,
                "verdict": language_verdict(usable, n),
                "wilson_interval": wilson_interval(usable, n),
            }
        low, high = result["wilson_interval"]
        lines.append(
            f"| {language} | {result['usable']}/{result['samples']} | "
            f"{low:.2f}–{high:.2f} | {result['verdict']} |"
        )
    if scale_summary and "c" in scale_summary.get("languages", {}):
        c = scale_summary["languages"]["c"]
        low, high = c["wilson_interval"]
        lines.extend(
            [
                "",
                f"Verified-C sample (BigVul-derived C-labelled rows are excluded): "
                f"{c['usable']}/{c['samples']} (95% Wilson {low:.2f}–{high:.2f}, "
                f"{c['verdict']}).",
            ]
        )
    python_wrapped_summaries = python_wrapped_summaries or {}
    wrapped_spike = python_wrapped_summaries.get("spike", {}).get("languages", {}).get("python")
    wrapped_scale = python_wrapped_summaries.get("scale", {}).get("languages", {}).get("python")
    if wrapped_spike and wrapped_scale:
        wrapped_n = wrapped_spike["samples"] + wrapped_scale["samples"]
        wrapped_usable = wrapped_spike["usable"] + wrapped_scale["usable"]
        low, high = wilson_interval(wrapped_usable, wrapped_n)
        raw_python = summary.get("languages", {}).get("python", {})
        raw_python_n = raw_python.get("samples", 0)
        raw_python_usable = raw_python.get("usable", 0)
        if python_scale_summary:
            scale_python = python_scale_summary.get("languages", {}).get("python", {})
            raw_python_usable += scale_python.get("usable", 0)
            raw_python_n = raw_python.get("samples", 0) + scale_python.get("samples", 0)
        raw_low, raw_high = wilson_interval(raw_python_usable, raw_python_n)
        spike_wrapped_count = (
            python_wrapped_summaries["spike"]
            .get("python_context_wrap", {})
            .get("wrapped_samples", 0)
        )
        scale_wrapped_count = (
            python_wrapped_summaries["scale"]
            .get("python_context_wrap", {})
            .get("wrapped_samples", 0)
        )
        lines.extend(
            [
                "",
                "### Python context-wrapper experiment (triage-only)",
                "",
                (
                    f"Raw excerpts: {raw_python_usable}/{raw_python_n} usable "
                    f"(95% Wilson {raw_low:.2f}–{raw_high:.2f}, "
                    f"{language_verdict(raw_python_usable, raw_python_n)})."
                ),
                (
                    f"With a synthetic class context applied only when the baseline graph had no "
                    f"real METHOD: {wrapped_usable}/{wrapped_n} usable "
                    f"(95% Wilson {low:.2f}–{high:.2f}, "
                    f"{language_verdict(wrapped_usable, wrapped_n)}); wrapped "
                    f"{spike_wrapped_count} original and {scale_wrapped_count} "
                    f"scale samples."
                ),
                (
                    "This is transformed evidence, not the production verdict: the wrapper adds a "
                    "source line and requires source-line mapping validation before adoption. "
                    "Recommendation: apply this wrapper to every indented Python method excerpt "
                    "in the production path and correct its line offset. Python remains NO-GO "
                    "until that path is implemented and verified."
                ),
            ]
        )
    lines.extend(["", "## Automatic cause counts", ""])
    cause_sources: dict[str, list[dict[str, int]]] = {
        "Python raw (spike + scale)": [
            summary.get("languages", {}).get("python", {}).get("cause_counts", {}),
        ],
        "C (verified scale only)": [],
        "C++": [summary.get("languages", {}).get("cpp", {}).get("cause_counts", {})],
    }
    if python_scale_summary:
        cause_sources["Python raw (spike + scale)"].append(
            python_scale_summary.get("languages", {}).get("python", {}).get("cause_counts", {})
        )
    if scale_summary:
        cause_sources["C (verified scale only)"].append(
            scale_summary.get("languages", {}).get("c", {}).get("cause_counts", {})
        )
    for language, sources in cause_sources.items():
        merged: dict[str, int] = {}
        for source in sources:
            for cause, count in source.items():
                merged[cause] = merged.get(cause, 0) + count
        counts = ", ".join(f"`{cause}` {count}" for cause, count in sorted(merged.items()))
        lines.append(f"- **{language}:** {counts or 'no automatic causes'}")

    cause_coded = [row for row in review_rows if row.get("human_cause")]
    agreement = sum(row.get("human_cause") == row.get("auto_cause") for row in cause_coded)
    lines.extend(
        [
            "",
            "## Manual review",
            "",
            f"Rows reviewed: {len(review_rows)}; cause-coded auto/human agreement: "
            f"{agreement}/{len(cause_coded)}"
            + (f" ({agreement / len(cause_coded):.1%})." if cause_coded else ".")
            + f" {len(review_rows) - len(cause_coded)} clean control rows have no assigned cause.",
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
    stub_languages = dict(summary.get("stub_rule", {}).get("by_language", {}))
    if scale_summary and "c" in scale_summary.get("stub_rule", {}).get("by_language", {}):
        stub_languages["verified c-scale"] = scale_summary["stub_rule"]["by_language"]["c"]
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
                "- **H1 — contradicted:** all 13 empty-DDG spike samples also have zero production "
                "REACHING_DEF edges; this was not only a DOT-view problem."
            ),
            (
                "- **H2 — partly tested; full count comparison remains open:** the production and "
                "spike paths agree on DDG/REACHING_DEF presence for the original samples, but "
                "their full node/edge graph counts were not compared."
            ),
            (
                "- **H3 — contradicted:** each of the 30 audit UNKNOWN flags corresponds to a "
                "production UNKNOWN node (Python 17/17, legacy C-labelled 8/8, C++ 5/5)."
            ),
            (
                "- **H4 — partly supported:** manual review found an expected-no-flow case, but "
                "the empty-DDG set also includes parse/context fragments; C/C++ flow estimates "
                "are approximate."
            ),
            "- **H5 — supported in reviewed samples:** source fragments/context gaps were manually "
            "confirmed, including five failures in verified C; see the review sheet.",
            (
                "- **H6 — contradicted:** Python has line-less operator METHODs; Rule B drops "
                "flow edges and increases components in 13/20 original Python samples."
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
                "with the original only as a clearly labeled extension. The Python wrapper "
                "experiment is triage-only; it does not silently alter the raw-path verdict."
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
    python_wrapped_summaries = {}
    for sample_set in ("spike", "scale"):
        wrapped_path = JOERN_TRIAGE_DIR / f"python_{sample_set}_wrapped" / "summary.json"
        if wrapped_path.is_file():
            python_wrapped_summaries[sample_set] = json.loads(
                wrapped_path.read_text(encoding="utf-8")
            )
    python_scale_path = JOERN_TRIAGE_DIR / "python_scale" / "summary.json"
    python_scale_summary = (
        json.loads(python_scale_path.read_text(encoding="utf-8"))
        if python_scale_path.is_file()
        else None
    )
    text = _report_text(
        rows, summary, reviews, scale_summary, python_wrapped_summaries, python_scale_summary
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    final_summary = dict(summary)
    final_languages = dict(summary.get("languages", {}))
    if python_scale_summary and "python" in final_languages:
        original_python = final_languages["python"]
        scale_python = python_scale_summary.get("languages", {}).get("python", {})
        n = original_python["samples"] + scale_python.get("samples", 0)
        usable = original_python["usable"] + scale_python.get("usable", 0)
        final_languages["python"] = {
            "samples": n,
            "usable": usable,
            "verdict": language_verdict(usable, n),
            "wilson_interval": wilson_interval(usable, n),
        }
    if scale_summary and "c" in scale_summary.get("languages", {}):
        final_languages["c"] = scale_summary["languages"]["c"]
    final_summary["languages"] = final_languages
    wrapped_spike = python_wrapped_summaries.get("spike", {}).get("languages", {}).get("python")
    wrapped_scale = python_wrapped_summaries.get("scale", {}).get("languages", {}).get("python")
    if wrapped_spike and wrapped_scale:
        final_summary["python_context_wrap_experiment"] = {
            "usable": wrapped_spike["usable"] + wrapped_scale["usable"],
            "samples": wrapped_spike["samples"] + wrapped_scale["samples"],
        }
    addendum = _addendum(final_summary)
    print(f"Wrote {output_path}")
    print("\nAddendum text for docs/graphs/joern_spike.md:\n")
    print(addendum)
    return text


def _output_dir(sample_set: str, group: str | None, python_context_wrap: bool = False) -> Path:
    if python_context_wrap:
        return JOERN_TRIAGE_DIR / f"{group or 'all'}_{sample_set}_wrapped"
    if sample_set == "spike":
        return JOERN_TRIAGE_DIR
    if sample_set == "c-scale":
        return JOERN_TRIAGE_DIR / "c_scale"
    return JOERN_TRIAGE_DIR / f"{group or 'all'}_scale"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("extract", "analyze"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--sample-set", choices=("spike", "scale", "c-scale"), default="spike")
        sub.add_argument("--group", choices=("python", "c", "cpp"))
        sub.add_argument(
            "--n", type=int, default=100, help="Scale samples per group (default: 100)"
        )
        sub.add_argument("--seed", type=int, default=43)
        sub.add_argument(
            "--python-context-wrap",
            action="store_true",
            help="Restore a synthetic class around parseable indented Python methods",
        )
        if name == "analyze":
            sub.add_argument("--spike-root", type=Path, default=SPIKE_DIR)
            sub.add_argument("--cache-root", type=Path, default=GRAPH_CACHE_DIR)
            sub.add_argument("--output-dir", type=Path)
    subparsers.add_parser("report")
    args = parser.parse_args(argv)

    if getattr(args, "python_context_wrap", False) and (
        args.sample_set not in {"scale", "spike"} or args.group != "python"
    ):
        parser.error("--python-context-wrap requires --sample-set scale|spike --group python")

    if args.command == "extract":
        extract_samples(
            sample_set=args.sample_set,
            group=args.group,
            n=args.n,
            seed=args.seed,
            python_context_wrap=args.python_context_wrap,
        )
    elif args.command == "analyze":
        analyze_samples(
            spike_root=args.spike_root,
            cache_root=args.cache_root,
            output_dir=args.output_dir
            or _output_dir(args.sample_set, args.group, args.python_context_wrap),
            sample_set=args.sample_set,
            group=args.group,
            n=args.n,
            seed=args.seed,
            python_context_wrap=args.python_context_wrap,
        )
    else:
        report()


if __name__ == "__main__":
    main()
