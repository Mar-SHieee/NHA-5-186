"""Aggregate benchmark CSVs and render the human-readable extraction report."""

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

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
            _number(r, "ok_count") / max(_number(r, "ok_count") + _number(r, "fail_count"), 1)
            for r in reps
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
            success_rate=statistics.mean(rates),
            median_peak_mib=statistics.median(peaks) if peaks else None,
        )
        output.append(row)

    # Compare every configuration with the matching one-worker A baseline.
    baselines = {
        (r["experiment"], r["group"], r["set_name"]): r["median_wall_seconds"]
        for r in output
        if r["variant"] == "A" and r["workers"] == "1" and r["batch_size"] == "1"
    }
    for row in output:
        baseline = baselines.get((row["experiment"], row["group"], row["set_name"]))
        row["speedup"] = baseline / row["median_wall_seconds"] if baseline else None
        workers = max(int(row["workers"] or 1), 1)
        row["efficiency"] = row["speedup"] / workers if row["speedup"] is not None else None
    return output


def projection_rows(
    configurations: dict[str, dict[str, float]],
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
                rows.append(
                    {
                        "scenario": scenario,
                        "language": group,
                        "rows": count,
                        "config": config,
                        "samples_per_second": throughput,
                        "hours_median": count / throughput / 3600 if throughput > 0 else None,
                        "hours_pessimistic": count * p95 / 3600 if p95 > 0 else None,
                        "rows_per_night": int(throughput * 36000) if throughput > 0 else None,
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


def render_report(
    results: list[dict[str, str]],
    samples: list[dict[str, str]],
    environment: dict[str, Any],
    manifest: dict[str, Any] | list[dict[str, str]],
    projections: list[dict[str, Any]] | None = None,
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
        if not subset:
            lines += ["not run", ""]
        else:
            vals = [
                [
                    r["variant"],
                    r["group"],
                    r["workers"],
                    f"{r['median_wall_seconds']:.3f}",
                    f"{r['success_rate']:.1%}",
                    r["median_peak_mib"] or "",
                ]
                for r in subset
            ]
            lines += [
                _table(
                    ["Variant", "Group", "Workers", "Median wall (s)", "Success", "Peak MiB"], vals
                ),
                "",
            ]
    lines += ["### 1.9 How long for N rows", ""]
    if projections:
        vals = [
            [
                r[k] if r.get(k) is not None else "not run"
                for k in (
                    "scenario",
                    "language",
                    "rows",
                    "config",
                    "samples_per_second",
                    "hours_median",
                    "hours_pessimistic",
                    "rows_per_night",
                )
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
        "not run: no decision-grade measurements are present yet.",
        "",
        "### 1.11 Hypotheses and limitations",
        "",
        "H1–H4 verdicts are not run until the corresponding experiments are recorded.",
        "",
    ]
    return "\n".join(lines)


def scenario_counts(interim_dir: Path = INTERIM_DIR) -> tuple[dict[str, dict[str, int]], str]:
    """Read present deduped parquet counts, with an explicit labelled plan fallback."""
    import pandas as pd

    sources = {
        "python": ["cvefixes_python_deduped.parquet"],
        "c": ["bigvul_deduped.parquet", "cvefixes_cpp_deduped.parquet"],
        "cpp": ["megavul_deduped.parquet"],
    }
    counts: dict[str, dict[str, int]] = {}
    if any(not (interim_dir / f).exists() for names in sources.values() for f in names):
        return {}, "fallback (plan estimates; parquet counts unavailable)"
    for group, filenames in sources.items():
        frames = [pd.read_parquet(interim_dir / name, columns=["label"]) for name in filenames]
        total = sum(len(frame) for frame in frames)
        vulnerable = sum(int((frame["label"] == 1).sum()) for frame in frames)
        counts[group] = {
            "S1": total,
            "S2": vulnerable,
            "S3": vulnerable * 2,
            "S4": vulnerable * 4,
            "S5": total if group == "python" else 0,
        }
    return counts, "parquet counts"


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
    aggregated = aggregate_results(results)
    counts, count_source = scenario_counts()
    scenario_map = {
        scenario: {group: values[scenario] for group, values in counts.items()}
        for scenario in ("S1", "S2", "S3", "S4", "S5")
    }
    if count_source != "parquet counts":
        environment["scenario_counts"] = count_source
    projection_data = _projection_configs(aggregated, samples)
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
            render_report(results, samples, environment, manifest_rows, projections),
        ),
        encoding="utf-8",
    )
    print(f"wrote {REPORT_PATH} and {SUMMARY_PATH} ({len(aggregated)} configurations)")


def _read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open(newline="", encoding="utf-8"))) if path.exists() else []


def _projection_configs(
    aggregated: list[dict[str, Any]], sample_rows: list[dict[str, str]]
) -> dict[str, dict[str, float]]:
    """Use the fastest measured E5 config per group and its observed per-sample p95."""
    candidates = [row for row in aggregated if row["experiment"] == "E5" and row["throughput"] > 0]
    selected: dict[str, dict[str, float]] = {}
    for group in {row["group"] for row in candidates}:
        best = max(
            (row for row in candidates if row["group"] == group), key=lambda r: r["throughput"]
        )
        run_ids = {
            row["run_id"]
            for row in _read_csv(BENCHMARK_DIR / "results.csv")
            if row.get("experiment") == "E5"
            and row.get("group") == group
            and row.get("variant") == best["variant"]
            and row.get("workers") == best["workers"]
            and row.get("batch_size") == best["batch_size"]
            and int(_number(row, "rep", -1)) >= 1
        }
        seconds = sorted(
            _number(sample, "seconds")
            for sample in sample_rows
            if sample.get("run_id") in run_ids and sample.get("ok", "").lower() in {"1", "true"}
        )
        p95 = seconds[max(0, (95 * len(seconds) + 99) // 100 - 1)] if seconds else 0
        selected[group] = {
            "throughput": best["throughput"],
            "p95_seconds_per_sample": p95,
            "group": group,
        }
    return selected


if __name__ == "__main__":
    main()
