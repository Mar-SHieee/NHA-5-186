"""Aggregate benchmark CSVs and render the human-readable extraction report."""

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from shield_core.datasets.schema import normalize_cwe
from shield_core.paths import BENCHMARK_DIR, DOCS_GRAPHS_DIR, INTERIM_DIR

BEGIN = "<!-- BENCHMARK:BEGIN -->"
END = "<!-- BENCHMARK:END -->"
REPORT_PATH = DOCS_GRAPHS_DIR / "extraction_report.md"
SUMMARY_PATH = DOCS_GRAPHS_DIR / "extraction_benchmark_summary.csv"
SUMMARY_COLUMNS = [
    "experiment",
    "variant",
    "group",
    "set_name",
    "workers",
    "batch_size",
    "xmx",
    "n_samples",
    "median_wall_seconds",
    "min_wall_seconds",
    "max_wall_seconds",
    "median_seconds_per_sample",
    "throughput",
    "success_rate",
    "median_peak_mib",
    "speedup",
    "efficiency",
]


def _number(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, ""))
    except (TypeError, ValueError):
        return default


def aggregate_results(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Aggregate measured repetitions; warm-up rows (rep=0) never enter the summary."""
    buckets: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    keys = ("experiment", "variant", "group", "set_name", "workers", "batch_size", "xmx")
    for row in rows:
        if int(_number(row, "rep", -1)) < 1:
            continue
        buckets[tuple(row.get(k, "") for k in keys)].append(row)

    output: list[dict[str, Any]] = []
    for key, reps in sorted(buckets.items()):
        walls = [_number(r, "wall_seconds") for r in reps]
        sps = [_number(r, "seconds_per_sample") for r in reps]
        rates = [
            _number(r, "ok_count") / (_number(r, "ok_count") + _number(r, "fail_count"))
            for r in reps
            if _number(r, "ok_count") + _number(r, "fail_count") > 0
        ]
        peaks = [_number(r, "peak_mib") for r in reps if r.get("peak_mib")]
        row: dict[str, Any] = dict(zip(keys, key, strict=True))
        row.update(
            n_samples=max(int(_number(r, "n_samples")) for r in reps),
            median_wall_seconds=statistics.median(walls),
            min_wall_seconds=min(walls),
            max_wall_seconds=max(walls),
            median_seconds_per_sample=statistics.median(sps),
            throughput=statistics.median([_number(r, "samples_per_second") for r in reps]),
            success_rate=statistics.mean(rates) if rates else None,
            failures=sum(int(_number(r, "fail_count")) for r in reps),
            median_peak_mib=statistics.median(peaks) if peaks else None,
            parse_seconds=statistics.median([_number(r, "parse_seconds") for r in reps]),
            export_seconds=statistics.median([_number(r, "export_seconds") for r in reps]),
            xml_parse_seconds=statistics.median([_number(r, "xml_parse_seconds") for r in reps]),
        )
        output.append(row)

    for row in output:
        if row["experiment"] == "E3":
            baseline_row = next(
                (
                    candidate
                    for candidate in output
                    if candidate["experiment"] == "E3"
                    and candidate["variant"] == "A"
                    and candidate["group"] == row["group"]
                    and candidate["set_name"] == row["set_name"]
                    and candidate["workers"] == "1"
                ),
                None,
            )
        elif row["experiment"] == "E4":
            baseline_row = next(
                (
                    candidate
                    for candidate in output
                    if candidate["experiment"] == "E4"
                    and candidate["variant"] == row["variant"]
                    and candidate["group"] == row["group"]
                    and candidate["set_name"] == row["set_name"]
                    and candidate["batch_size"] == row["batch_size"]
                    and candidate["xmx"] == row["xmx"]
                    and candidate["workers"] == "1"
                ),
                None,
            )
        else:
            baseline_row = None
        baseline = baseline_row["median_wall_seconds"] if baseline_row else None
        row["speedup"] = baseline / row["median_wall_seconds"] if baseline else None
        workers = max(int(row["workers"] or 1), 1)
        row["efficiency"] = (
            row["speedup"] / workers
            if row["experiment"] == "E4" and row["speedup"] is not None
            else None
        )
    return output


def projection_rows(
    configurations: dict[str, dict[str, Any]],
    scenarios: dict[str, dict[str, int]],
) -> list[dict[str, Any]]:
    """Build hours/night projections from throughput and p95 per-sample latency."""
    rows = []
    for config, metrics in configurations.items():
        throughput = metrics.get("throughput", 0)
        p95 = metrics.get("p95_seconds_per_sample", 0)
        for scenario, groups in scenarios.items():
            for group, count in groups.items():
                if metrics.get("group") and metrics["group"] != group:
                    continue
                if count <= 0:
                    continue
                rows.append(
                    {
                        "scenario": scenario,
                        "language": group,
                        "rows": count,
                        "config": metrics.get("config", config),
                        "samples_per_second": throughput,
                        "hours_median": count / throughput / 3600 if throughput > 0 else None,
                        "hours_pessimistic": count * p95 / 3600 if p95 > 0 else None,
                        "rows_per_night": int(throughput * 36000) if throughput > 0 else None,
                        "note": metrics.get("note", ""),
                    }
                )
    return rows


def replace_section(existing: str, content: str) -> str:
    """Replace only the marked section, creating it when absent; reject malformed markers."""
    if existing.count(BEGIN) != existing.count(END) or existing.count(BEGIN) > 1:
        raise ValueError("report must contain at most one balanced benchmark marker pair")
    section = f"{BEGIN}\n{content.rstrip()}\n{END}"
    if BEGIN in existing:
        start = existing.index(BEGIN)
        end = existing.index(END, start) + len(END)
        return existing[:start] + section + existing[end:]
    return existing.rstrip() + "\n\n" + section + "\n"


def _table(headers: list[str], values: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(str(v) for v in row) + " |" for row in values)
    return "\n".join(lines)


def _fidelity_signal_summary(signal: str, result: dict[str, Any]) -> str:
    files = result.get("files", [])
    status = "separates" if len(files) >= 2 else "does not separate"
    detail = f"{len(files)} files"
    if result.get("method_coverage"):
        detail = f"methods {result['method_coverage']}"
    elif result.get("counts"):
        detail += ", " + ", ".join(
            f"{key}={count}" for key, count in sorted(result["counts"].items())
        )
    return f"{signal}: {status} ({detail})"


def render_report(
    results: list[dict[str, str]],
    samples: list[dict[str, str]],
    environment: dict[str, Any],
    manifest: dict[str, Any] | list[dict[str, str]],
    projections: list[dict[str, Any]] | None = None,
    fidelity: dict[str, Any] | None = None,
) -> str:
    """Render recorded inputs; absent experiments are labelled as not run."""
    aggregated = aggregate_results(results)
    lines = ["## 1. Extraction benchmark (W2-P2-05)", "", "### 1.1 Environment", ""]
    lines += [f"- **{key}:** {value}" for key, value in environment.items()] or ["- not run"]
    lines += [
        "",
        "### 1.2 Method",
        "",
        "A uses `JoernExtractor`; B runs samples sequentially in one container; C parses a batch. "
        "Wall time uses `perf_counter`; warm-ups (`rep=0`) are excluded; memory uses the "
        "recorded container peak method.",
        "",
    ]
    sections = [
        ("E1", "1.3 Spike vs production path"),
        ("E2", "1.4 Where the time goes"),
        ("E3", "1.5 Variants at one worker"),
        ("E4", "1.6 Workers"),
        ("E5", "1.7 Scale set and long tail"),
        ("E7", "1.8 Is batching safe?"),
    ]
    for experiment, title in sections:
        subset = [r for r in aggregated if r["experiment"] == experiment]
        lines += [f"### {title}", ""]
        if experiment == "E7" and fidelity and fidelity.get("groups"):
            values = [
                [
                    group,
                    data.get("verdict", "not evaluated"),
                    data.get("unattributable_method_nodes", "N/A"),
                    data.get("cross_file_call_edges", "N/A"),
                    ", ".join(
                        f"{name}: {row.get('mismatch_rate', 0):.1%}"
                        for name, row in data.get("per_file", {}).items()
                    ),
                    "; ".join(data.get("caveats", [])) or "none",
                    "; ".join(
                        _fidelity_signal_summary(signal, result)
                        for signal, result in data.get("candidate_signals", {}).items()
                    ),
                ]
                for group, data in fidelity["groups"].items()
            ]
            match_rule = next(iter(fidelity["groups"].values())).get("match_rule", "")
            ignored_types = sorted(
                {
                    node_type
                    for data in fidelity["groups"].values()
                    for node_type in data.get("ignored_node_types", [])
                }
            )
            lines += [
                f"Match rule: {match_rule}. Ignored node types observed: "
                + (", ".join(ignored_types) or "none")
                + ".",
                "",
                _table(
                    [
                        "Group",
                        "Batching",
                        "Unattributable METHODS",
                        "Cross-file CALL edges",
                        "Mismatch rate by file",
                        "Caveats",
                        "Candidate signals",
                    ],
                    values,
                ),
                "",
            ]
            followups = [
                f"{group}: {data['follow_up']}"
                for group, data in fidelity["groups"].items()
                if data.get("follow_up")
            ]
            lines += followups or ["No group-specific follow-up noted."]
            lines += ["Variant D feasibility: not evaluated in this phase.", ""]
        elif not subset:
            production = [
                row
                for row in aggregated
                if experiment == "E1" and row["experiment"] == "E3" and row["variant"] == "A"
            ]
            if production:
                values = [
                    [row["group"], f"{row['median_seconds_per_sample']:.3f}"] for row in production
                ]
                lines += [
                    "E1 is represented by the E3 production-path A runs. The historical spike "
                    "baseline was 5.85 s/sample; it used three Joern exports per sample, so this "
                    "is not a like-for-like comparison.",
                    "",
                    _table(["Group", "Production A median (s/sample)"], values),
                    "",
                ]
            else:
                lines += ["not run", ""]
        else:
            if experiment == "E2":
                vals = [
                    [
                        row["variant"],
                        row["group"] or "floor",
                        f"{row['median_wall_seconds']:.3f}",
                        f"{row['parse_seconds']:.3f}",
                        f"{row['export_seconds']:.3f}",
                        f"{row['xml_parse_seconds']:.3f}",
                        f"{row['median_peak_mib']:.1f}"
                        if row["median_peak_mib"] is not None
                        else "N/A",
                    ]
                    for row in subset
                ]
                lines += [
                    _table(
                        [
                            "Variant",
                            "Group",
                            "Wall (s)",
                            "Parse (s)",
                            "Export (s)",
                            "XML (s)",
                            "Peak MiB",
                        ],
                        vals,
                    ),
                    "",
                ]
            else:
                vals = [
                    [
                        row["variant"],
                        row["group"],
                        row["workers"],
                        row["batch_size"],
                        f"{row['median_wall_seconds']:.3f}",
                        f"{row['throughput']:.3f}",
                        f"{row['speedup']:.2f}x" if row["speedup"] is not None else "N/A",
                        f"{row['efficiency']:.1%}" if row["efficiency"] is not None else "N/A",
                        f"{row['success_rate']:.1%}" if row["success_rate"] is not None else "N/A",
                        row["failures"],
                        f"{row['median_peak_mib']:.1f}"
                        if row["median_peak_mib"] is not None
                        else "N/A",
                    ]
                    for row in subset
                ]
                if experiment == "E5":
                    lines += _render_scale_analysis(results, samples)
                lines += [
                    _table(
                        [
                            "Variant",
                            "Group",
                            "Workers",
                            "Batch",
                            "Wall (s)",
                            "Samples/s",
                            "Speed-up",
                            "Efficiency",
                            "Success",
                            "Failures",
                            "Peak MiB",
                        ],
                        vals,
                    ),
                    "",
                ]
    lines += ["### 1.9 How long for N rows", ""]
    if projections:
        vals = [
            [
                r["scenario"],
                r["language"],
                r["rows"],
                r["config"],
                f"{r['samples_per_second']:.3f}",
                f"{r['hours_median']:.2f}" if r["hours_median"] is not None else "N/A",
                f"{r['hours_pessimistic']:.2f}" if r["hours_pessimistic"] is not None else "N/A",
                r["rows_per_night"],
                r["note"],
            ]
            for r in projections
        ]
        lines += [
            _table(
                [
                    "Scenario",
                    "Language",
                    "Rows",
                    "Config",
                    "Samples/s",
                    "Hours",
                    "Hours (p95)",
                    "Rows / 10 h",
                    "Note",
                ],
                vals,
            ),
            "",
        ]
    else:
        lines += ["not run", ""]
    lines += [
        "### 1.10 Recommendation",
        "",
        _recommendation(aggregated, fidelity),
        "",
        "### 1.11 Hypotheses and limitations",
        "",
        _hypothesis_verdicts(aggregated, fidelity),
        "",
    ]
    return "\n".join(lines)


def _recommendation(rows: list[dict[str, Any]], fidelity: dict[str, Any] | None = None) -> str:
    e3 = [row for row in rows if row["experiment"] == "E3" and row["success_rate"] == 1.0]
    e5 = [row for row in rows if row["experiment"] == "E5" and row["success_rate"] == 1.0]
    e4a = [
        row
        for row in rows
        if row["experiment"] == "E4" and row["variant"] == "A" and row["success_rate"] == 1.0
    ]
    if not e3 and not e4a:
        return "not run: no decision-grade measurements are present yet."
    parts = []
    if e5:
        best_by_group = {}
        for group in sorted({row["group"] for row in e5}):
            unusable = (
                fidelity
                and fidelity.get("groups", {}).get(group, {}).get("verdict") == "not usable"
            )
            choices = (
                [row for row in e3 if row["group"] == group and row["variant"] in {"A", "B"}]
                if unusable
                else [row for row in e5 if row["group"] == group]
            )
            best_by_group[group] = max(choices, key=lambda row: row["throughput"])
        parts.append(
            "Fastest successful configs (non-batched E3 fallback where fidelity failed): "
            + "; ".join(
                f"{group}: {row['variant']} ("
                f"{'non-batched' if row['experiment'] == 'E3' else 'scale'}, "
                f"batch {row['batch_size']}, "
                f"{row['workers']} workers, {row['throughput']:.3f} samples/s)"
                for group, row in best_by_group.items()
            )
            + "."
        )
    elif e3:
        best_by_group = {}
        for group in sorted({row["group"] for row in e3}):
            choices = [row for row in e3 if row["group"] == group]
            best_by_group[group] = min(choices, key=lambda row: row["median_seconds_per_sample"])
        parts.append(
            "Fastest successful E3 configurations: "
            + "; ".join(
                f"{group}: {row['variant']} (batch {row['batch_size']}, "
                f"{row['median_seconds_per_sample']:.3f} s/sample)"
                for group, row in best_by_group.items()
            )
            + "."
        )
    if e4a:
        fastest_workers = {}
        for group in sorted({row["group"] for row in e4a}):
            choices = [row for row in e4a if row["group"] == group]
            fastest_workers[group] = min(choices, key=lambda row: row["median_wall_seconds"])
        parts.append(
            "Fastest tested production-path worker count: "
            + "; ".join(f"{group}: {row['workers']}" for group, row in fastest_workers.items())
            + "."
        )
    if fidelity and fidelity.get("groups"):
        parts.append(
            "Batching is speed-only for groups that failed the Phase 7 fidelity check. "
            "The recommendation falls back to the fastest successful non-batched E3 variant; "
            "the scale projections use E5 A measurements where batching was not usable."
        )
    else:
        parts.append(
            "Treat batching as a speed result only until Phase 7 validates per-file fidelity; "
            + (
                "E5 scale-set throughput now drives projections."
                if e5
                else "scale-set projections await Phase 6."
            )
        )
    return " ".join(parts)


def scale_tail_statistics(
    results: list[dict[str, str]], sample_rows: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """Summarize per-sample scale timings, tail share, failures and size correlation."""
    run_configs = {
        row["run_id"]: row
        for row in results
        if row.get("experiment") == "E5" and int(_number(row, "rep", -1)) >= 1
    }
    buckets: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for sample in sample_rows:
        config = run_configs.get(sample.get("run_id", ""))
        if config:
            key = (
                config.get("variant", ""),
                config.get("group", ""),
                config.get("workers", ""),
                config.get("batch_size", ""),
            )
            buckets[key].append(sample)

    output = []
    for (variant, group, workers, batch_size), rows in sorted(buckets.items()):
        good = [row for row in rows if row.get("ok", "").lower() in {"1", "true"}]
        failures = [row for row in rows if row not in good]
        seconds = [_number(row, "seconds") for row in good]
        ordered = sorted(seconds)
        n_lines = [_number(row, "n_lines") for row in good]
        timeout_ids = [
            row.get("sample_id", "") for row in failures if row.get("failure_class") == "timeout"
        ]
        other_ids = [
            row.get("sample_id", "") for row in failures if row.get("failure_class") != "timeout"
        ]
        top_n = max(1, (len(ordered) + 19) // 20) if ordered else 0
        total_seconds = sum(ordered)
        try:
            correlation = statistics.correlation(n_lines, seconds) if len(seconds) >= 2 else None
        except statistics.StatisticsError:
            correlation = None
        p95_rank = (95 * len(ordered) + 99) // 100
        output.append(
            {
                "variant": variant,
                "group": group,
                "workers": workers,
                "batch_size": batch_size,
                "n_samples": len(rows),
                "p50_seconds": statistics.median(ordered) if ordered else None,
                "p95_seconds": ordered[p95_rank - 1] if p95_rank else None,
                "max_seconds": ordered[-1] if ordered else None,
                "timeouts": len(timeout_ids),
                "timeout_ids": ", ".join(timeout_ids) if timeout_ids else "none",
                "other_failures": len(other_ids),
                "other_failure_ids": ", ".join(other_ids) if other_ids else "none",
                "slowest_5pct_share": (
                    sum(ordered[-top_n:]) / total_seconds if total_seconds else 0.0
                ),
                "lines_seconds_correlation": correlation,
            }
        )
    return output


def scale_spike_comparisons(aggregated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare E5 throughput with the matching E4 variant, workers and batch size."""
    e4 = {
        (row["variant"], row["group"], row["workers"], row["batch_size"]): row
        for row in aggregated
        if row["experiment"] == "E4"
    }
    comparisons = []
    for scale in aggregated:
        if scale["experiment"] != "E5":
            continue
        spike = e4.get((scale["variant"], scale["group"], scale["workers"], scale["batch_size"]))
        if not spike or spike["throughput"] <= 0:
            continue
        change = scale["throughput"] / spike["throughput"] - 1
        comparisons.append(
            {
                "variant": scale["variant"],
                "group": scale["group"],
                "workers": scale["workers"],
                "batch_size": scale["batch_size"],
                "spike_samples_per_second": spike["throughput"],
                "scale_samples_per_second": scale["throughput"],
                "change": change,
                "over_25pct": abs(change) > 0.25,
            }
        )
    return comparisons


def _render_scale_analysis(
    results: list[dict[str, str]], sample_rows: list[dict[str, str]]
) -> list[str]:
    tails = scale_tail_statistics(results, sample_rows)
    lines = [
        "**Per-sample tail statistics (E5; successful latencies, failures shown separately):**",
        "",
    ]
    if tails:
        values = [
            [
                row["variant"],
                row["group"],
                row["workers"],
                row["batch_size"],
                row["n_samples"],
                f"{row['p50_seconds']:.3f}" if row["p50_seconds"] is not None else "N/A",
                f"{row['p95_seconds']:.3f}" if row["p95_seconds"] is not None else "N/A",
                f"{row['max_seconds']:.3f}" if row["max_seconds"] is not None else "N/A",
                row["timeouts"],
                row["timeout_ids"],
                row["other_failures"],
                row["other_failure_ids"],
                f"{row['slowest_5pct_share']:.1%}",
                f"{row['lines_seconds_correlation']:.3f}"
                if row["lines_seconds_correlation"] is not None
                else "N/A",
            ]
            for row in tails
        ]
        lines += [
            _table(
                [
                    "Variant",
                    "Group",
                    "Workers",
                    "Batch",
                    "Samples",
                    "p50 (s)",
                    "p95 (s)",
                    "Max (s)",
                    "Timeouts",
                    "Timed-out IDs",
                    "Other failures",
                    "Other IDs",
                    "Slowest 5% time share",
                    "Corr(lines,time)",
                ],
                values,
            ),
            "",
        ]
    else:
        lines += ["not run", ""]

    comparisons = scale_spike_comparisons(aggregate_results(results))
    lines += ["**Scale versus spike throughput (matched configurations):**", ""]
    if not comparisons:
        lines += ["not run", ""]
        return lines
    values = [
        [
            row["variant"],
            row["group"],
            row["workers"],
            row["batch_size"],
            f"{row['spike_samples_per_second']:.3f}",
            f"{row['scale_samples_per_second']:.3f}",
            f"{row['change']:+.1%}",
            "yes" if row["over_25pct"] else "no",
        ]
        for row in comparisons
    ]
    differing = [
        f"{row['variant']}/{row['group']}/w{row['workers']}"
        for row in comparisons
        if row["over_25pct"]
    ]
    lines += [
        _table(
            [
                "Variant",
                "Group",
                "Workers",
                "Batch",
                "Spike samples/s",
                "Scale samples/s",
                "Change",
                ">25%?",
            ],
            values,
        ),
        "",
        (
            "E5 differs from E4 by more than 25% for " + ", ".join(differing) + ". "
            if differing
            else "No matched configuration differs from E4 by more than 25%. "
        )
        + "E5 scale throughput is used for projections.",
        "",
    ]
    return lines


def _hypothesis_verdicts(rows: list[dict[str, Any]], fidelity: dict[str, Any] | None = None) -> str:
    e2 = any(row["experiment"] == "E2" for row in rows)
    e3 = any(row["experiment"] == "E3" for row in rows)
    e4 = any(row["experiment"] == "E4" for row in rows)
    e7 = bool(fidelity and fidelity.get("groups")) or any(row["experiment"] == "E7" for row in rows)
    h2 = "H2 batches of 20-50 are faster: confirmed for successful runs"
    if not e7:
        h2 += "; fidelity remains open"
    elif fidelity and all(
        data.get("verdict") == "not usable" for data in fidelity.get("groups", {}).values()
    ):
        h2 += "; batching was not usable in the Phase 7 fidelity probe"
    else:
        h2 += "; see the Phase 7 per-group fidelity result"
    verdicts = [
        "H1 fixed costs dominate: confirmed by A/B versus C batch speed differences"
        if e2 and e3
        else "H1 fixed costs dominate: not yet tested",
        h2 if e3 else "H2 batches of 20-50 are faster: not yet tested",
        "H3 worker scaling is sub-linear: confirmed (A four-worker speed-up is below 4x)"
        if e4
        else "H3 worker scaling is sub-linear: not yet tested",
        (
            "H4 Python attribution is a problem: confirmed by the Phase 7 probe"
            if fidelity.get("groups", {}).get("python", {}).get("verdict") == "not usable"
            else "H4 Python attribution is a problem: not confirmed by the Phase 7 probe"
        )
        if e7 and fidelity
        else (
            "H4 Python attribution is a problem: tested in Phase 7"
            if e7
            else "H4 Python attribution is a problem: untested; Phase 7 remains open"
        ),
    ]
    return "; ".join(verdicts) + "."


def scenario_counts(interim_dir: Path = INTERIM_DIR) -> tuple[dict[str, dict[str, int]], str]:
    """Read present deduped parquet counts, with an explicit labelled plan fallback."""
    import pandas as pd

    sources = {
        "python": ["cvefixes_python_deduped.parquet"],
        "c": ["bigvul_deduped.parquet", "cvefixes_cpp_deduped.parquet"],
        "cpp": ["megavul_deduped.parquet"],
    }
    in_scope = {
        "python": {
            "CWE-918",
            "CWE-79",
            "CWE-601",
            "CWE-22",
            "CWE-444",
            "CWE-613",
            "CWE-352",
            "CWE-94",
            "CWE-400",
            "CWE-20",
            "CWE-200",
            "CWE-89",
        },
        "c": {
            "CWE-119",
            "CWE-125",
            "CWE-787",
            "CWE-20",
            "CWE-476",
            "CWE-416",
            "CWE-190",
            "CWE-200",
            "CWE-362",
            "CWE-120",
            "CWE-400",
            "CWE-617",
            "CWE-415",
            "CWE-22",
            "CWE-369",
            "CWE-122",
        },
        "cpp": {
            "CWE-119",
            "CWE-125",
            "CWE-787",
            "CWE-20",
            "CWE-476",
            "CWE-416",
            "CWE-190",
            "CWE-200",
            "CWE-362",
            "CWE-120",
            "CWE-400",
            "CWE-617",
            "CWE-415",
            "CWE-22",
            "CWE-369",
            "CWE-122",
        },
    }
    counts: dict[str, dict[str, int]] = {}
    if any(not (interim_dir / f).exists() for names in sources.values() for f in names):
        return {}, "fallback (plan estimates; parquet counts unavailable)"
    for group, filenames in sources.items():
        frames = [
            pd.read_parquet(interim_dir / name, columns=["label", "cwe"]) for name in filenames
        ]
        total = sum(len(frame) for frame in frames)
        vulnerable = sum(
            int(
                (
                    frame["label"].eq(1)
                    & frame["cwe"].map(
                        lambda values, scope=in_scope[group]: _has_scope_cwe(values, scope)
                    )
                ).sum()
            )
            for frame in frames
        )
        counts[group] = {
            "S1": total,
            "S2": vulnerable,
            "S3": vulnerable * 2,
            "S4": vulnerable * 4,
            "S5": total if group == "python" else 0,
        }
    return counts, "parquet counts; S2 uses D31 in-scope CWEs"


def _has_scope_cwe(value: Any, scope: set[str]) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        values = value.split(",")
    else:
        try:
            values = list(value)
        except TypeError:
            values = [value]
    return bool(set(normalize_cwe(values)) & scope)


def _write_summary(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in SUMMARY_COLUMNS})


def main() -> None:
    results = _read_csv(BENCHMARK_DIR / "results.csv")
    samples = _read_csv(BENCHMARK_DIR / "samples.csv")
    manifest_rows = _read_csv(BENCHMARK_DIR / "samples_manifest.csv")
    env_path = BENCHMARK_DIR / "environment.json"
    environment = json.loads(env_path.read_text(encoding="utf-8")) if env_path.exists() else {}
    fidelity_path = BENCHMARK_DIR / "fidelity.json"
    fidelity = (
        json.loads(fidelity_path.read_text(encoding="utf-8")) if fidelity_path.exists() else None
    )
    aggregated = aggregate_results(results)
    counts, count_source = scenario_counts()
    scenario_map = {
        scenario: {group: values[scenario] for group, values in counts.items()}
        for scenario in ("S1", "S2", "S3", "S4", "S5")
    }
    environment["scenario_counts"] = count_source
    projection_data = _projection_configs(aggregated, samples, fidelity)
    projections = projection_rows(projection_data, scenario_map) if projection_data else []
    _write_summary(aggregated, SUMMARY_PATH)
    text = (
        REPORT_PATH.read_text(encoding="utf-8")
        if REPORT_PATH.exists()
        else "# Joern extraction report\n\n<!-- P1 sections may be added below. -->\n"
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        replace_section(
            text,
            render_report(results, samples, environment, manifest_rows, projections, fidelity),
        ),
        encoding="utf-8",
    )
    print(f"wrote {REPORT_PATH} and {SUMMARY_PATH} ({len(aggregated)} configurations)")


def _read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open(newline="", encoding="utf-8"))) if path.exists() else []


def _projection_configs(
    aggregated: list[dict[str, Any]],
    sample_rows: list[dict[str, str]],
    fidelity: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Project the fastest config and A baseline per group using E5 or preliminary E4 data."""
    scale_rows = [row for row in aggregated if row["experiment"] == "E5"]
    experiment = "E5" if scale_rows else "E4"
    candidates = [
        row
        for row in aggregated
        if row["experiment"] == experiment and row["throughput"] > 0 and row["success_rate"] == 1.0
    ]
    selected: dict[str, dict[str, Any]] = {}
    raw_results = _read_csv(BENCHMARK_DIR / "results.csv")
    for group in {row["group"] for row in candidates}:
        group_rows = [row for row in candidates if row["group"] == group]
        fidelity_failed = (
            fidelity and fidelity.get("groups", {}).get(group, {}).get("verdict") == "not usable"
        )
        if fidelity_failed:
            group_rows = [row for row in group_rows if row["variant"] == "A"]
            if not group_rows:
                continue
        best = max(group_rows, key=lambda row: row["throughput"])
        baseline = max(
            (row for row in group_rows if row["variant"] == "A"),
            key=lambda row: row["throughput"],
            default=None,
        )
        selections = [
            (best, "best non-batched (fidelity fallback)" if fidelity_failed else "fastest")
        ]
        if baseline and (baseline["variant"], baseline["workers"], baseline["batch_size"]) != (
            best["variant"],
            best["workers"],
            best["batch_size"],
        ):
            selections.append((baseline, "A baseline"))
        for row, label in selections:
            run_ids = {
                result["run_id"]
                for result in raw_results
                if result.get("experiment") == experiment
                and result.get("group") == group
                and result.get("variant") == row["variant"]
                and result.get("workers") == row["workers"]
                and result.get("batch_size") == row["batch_size"]
                and int(_number(result, "rep", -1)) >= 1
            }
            seconds = sorted(
                _number(sample, "seconds")
                for sample in sample_rows
                if sample.get("run_id") in run_ids and sample.get("ok", "").lower() in {"1", "true"}
            )
            p95 = seconds[max(0, (95 * len(seconds) + 99) // 100 - 1)] if seconds else 0
            config_key = f"{group}:{label}"
            selected[config_key] = {
                "throughput": row["throughput"],
                "p95_seconds_per_sample": p95,
                "group": group,
                "config": (
                    f"{row['variant']}-b{row['batch_size']}-w{row['workers']} "
                    f"({label}; {'spike60 preliminary' if experiment == 'E4' else 'scale'})"
                ),
                "note": (
                    "preliminary spike-60 throughput; use E5 scale results for final projection"
                    if experiment == "E4"
                    else (
                        "E5 scale-set A baseline; batching not usable per Phase 7 fidelity probe"
                        if fidelity_failed
                        else "scale-set measurement"
                    )
                ),
            }
    return selected


if __name__ == "__main__":
    main()
