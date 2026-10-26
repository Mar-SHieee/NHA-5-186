"""Diagnose why CVEfixes commits are absent from function-level datasets.

  * datasets   : every folder in data/raw/ that holds fixes.csv, file_change.csv and
                 method_change.csv; its loader output is data/interim/<folder>.parquet
  * languages  : the ones present in that folder's file_change.csv (override: --languages)
  * diagnoses  : built from the counts observed for each absent commit, so only the
                 situations that really occur appear in the report

Run from the repository root:
    python scripts/data_audit/check_cvefixes_absent_commits.py      # every dataset found
    python scripts/data_audit/check_cvefixes_absent_commits.py cvefixes_cpp  # one folder (or: cpp)
    python scripts/data_audit/check_cvefixes_absent_commits.py cpp --languages c,c++ \
        --examples 10 --full

Output: docs/<folder>_absent_commits.md (overwritten on every run).
"""

from __future__ import annotations

import argparse
import random
import re

import pandas as pd

from shield_core.paths import DOCS_EXPLORATION_DIR, REPO_ROOT

ROOT = REPO_ROOT
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
DOCS = DOCS_EXPLORATION_DIR

REQUIRED_TABLES = ("fixes.csv", "file_change.csv", "method_change.csv")
LINE_COLUMNS = ("num_lines_added", "num_lines_deleted")
SEED = 42


# ---------------------------------------------------------------- helpers
def normalize_text(series: pd.Series) -> pd.Series:
    """Normalize text while preserving missing values as missing."""
    return series.astype("string").str.strip().str.lower()


def valid_values(series: pd.Series) -> pd.Series:
    values = normalize_text(series)
    return values[values.notna() & values.ne("") & values.ne("nan")]


def markdown_table(df: pd.DataFrame) -> list[str]:
    """Render a DataFrame as a Markdown table, safely handling non-strings."""
    if df.empty:
        return ["_No rows._", ""]
    safe = (
        df.fillna("-")
        .astype(str)
        .apply(
            lambda col: col.str.replace("|", r"\|", regex=False).str.replace("\n", " ", regex=False)
        )
    )
    lines = [
        "| " + " | ".join(safe.columns) + " |",
        "| " + " | ".join("---" for _ in safe.columns) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in safe.itertuples(index=False, name=None))
    lines.append("")
    return lines


def commit_url(repo_url, commit) -> str:
    if repo_url is None or pd.isna(repo_url):
        return str(commit)
    return f"{str(repo_url).strip().rstrip('/')}/commit/{commit}"


def discover() -> list[str]:
    if not RAW.is_dir():
        return []
    return sorted(
        d.name
        for d in RAW.iterdir()
        if d.is_dir() and all((d / t).exists() for t in REQUIRED_TABLES)
    )


def resolve_name(arg: str) -> str:
    for candidate in (arg, f"cvefixes_{arg}"):
        if (RAW / candidate).is_dir():
            return candidate
    raise SystemExit(f"No folder data/raw/{arg} (or data/raw/cvefixes_{arg})")


def diagnose(row: pd.Series) -> str:
    """Describe what the raw tables show for one commit. Built from counts only."""
    if row.file_change_rows == 0:
        return "no file-change rows for this commit"
    if row.target_file_rows == 0:
        return "file changes exist, but none in the target language(s)"
    if row.method_change_rows == 0:
        return "target-language files exist, but no function rows"
    if row.before_change_true > 0:
        return (
            "has old-version function rows but is absent from the output "
            "(look for a later loader filter or join)"
        )
    if row.before_change_false > 0 and row.before_change_unknown == 0:
        return "function rows exist, but only new-version ones (before_change=False)"
    return "function rows exist, but before_change values are missing or unrecognized"


def zero_deleted(values: pd.Series) -> str:
    known = values.dropna()
    if known.empty:
        return "-"
    return f"{100 * (known == 0).mean():.1f}% of {len(known):,}"


# ------------------------------------------------- did the function exist before?
def existed_before(raw, target_files, commits, method_change, examples, rng, repo_of):
    """For commits with only new-version function rows: was each function already in the old file?

    A name that never appears in the old file is a new function. A name that does appear
    means the function (or a call to it) was already there, so the fix most likely added
    lines inside an existing function. This is a name match, not a parse.
    """
    files = target_files.loc[
        target_files["hash_norm"].isin(commits), ["file_change_id", "hash_norm"]
    ]
    ids = set(files["file_change_id"])
    old_code = {}
    for chunk in pd.read_csv(
        raw / "file_change.csv",
        usecols=["file_change_id", "code_before"],
        chunksize=2000,
        low_memory=False,
    ):
        chunk = chunk[chunk["file_change_id"].isin(ids)]
        old_code.update(zip(chunk["file_change_id"], chunk["code_before"], strict=False))

    methods = method_change[
        method_change["file_change_id"].isin(ids) & method_change["before_flag"].eq("false")
    ].merge(files, on="file_change_id")

    def seen(row) -> bool:
        base = re.split(r"::|\.", str(row["name"]))[-1]
        old = old_code.get(row["file_change_id"])
        if not base or not isinstance(old, str):
            return False
        return re.search(r"\b" + re.escape(base) + r"\b", old) is not None

    methods["existed"] = methods.apply(seen, axis=1)
    per_commit = methods.groupby("hash_norm")["existed"].agg(["sum", "count"])
    kind = pd.Series("mixed", index=per_commit.index)
    kind[per_commit["sum"] == 0] = "all new (name not in the old file)"
    kind[per_commit["sum"] == per_commit["count"]] = "all existed (name in the old file)"

    lines = [
        "## New-version-only commits: were the functions already in the old file?",
        "",
        "A name that never appears in the old file is a new function (nothing was lost). A name "
        "that does appear means the function was already there, so the fix most likely added "
        "lines inside it and its vulnerable version is missing from the dataset. This is a name "
        "match, not a parse: strong evidence, not proof.",
        "",
    ]
    counts = kind.value_counts().rename_axis("kind").reset_index(name="commits")
    counts["share"] = (100 * counts["commits"] / len(kind)).map(lambda x: f"{x:.1f}%")
    lines += markdown_table(counts)
    for label in counts["kind"]:
        members = sorted(kind[kind == label].index)
        picked = sorted(rng.sample(members, min(examples, len(members))))
        lines += (
            [f"### {label}", ""] + [f"- {commit_url(repo_of.get(c), c)}" for c in picked] + [""]
        )
    return lines


# ------------------------------------------------------------------- main work
def run(name: str, languages: set[str] | None, examples: int, full: bool) -> None:
    raw = RAW / name
    dataset_path = INTERIM / f"{name}.parquet"
    for path in [raw / t for t in REQUIRED_TABLES] + [dataset_path]:
        if not path.exists():
            raise FileNotFoundError(f"Missing required file: {path}")

    fc_header = pd.read_csv(raw / "file_change.csv", nrows=0).columns
    mc_header = pd.read_csv(raw / "method_change.csv", nrows=0).columns
    line_cols = [c for c in LINE_COLUMNS if c in fc_header]

    fixes = pd.read_csv(
        raw / "fixes.csv", usecols=lambda c: c in {"cve_id", "hash", "repo_url"}, low_memory=False
    )
    file_change = pd.read_csv(
        raw / "file_change.csv",
        usecols=["file_change_id", "hash", "programming_language"] + line_cols,
        low_memory=False,
    )
    method_change = pd.read_csv(
        raw / "method_change.csv",
        usecols=["file_change_id", "before_change"] + (["name"] if "name" in mc_header else []),
        low_memory=False,
    )
    dataset = pd.read_parquet(dataset_path, columns=["commit"])

    fixes["hash_norm"] = normalize_text(fixes["hash"])
    file_change["hash_norm"] = normalize_text(file_change["hash"])
    method_change["before_flag"] = normalize_text(method_change["before_change"])

    dataset_hashes = set(valid_values(dataset["commit"]))
    fix_hashes = set(valid_values(fixes["hash"]))
    absent = sorted(fix_hashes - dataset_hashes)
    present = fix_hashes & dataset_hashes

    language = normalize_text(file_change["programming_language"])
    if languages is None:
        languages = set(valid_values(file_change["programming_language"]).unique())
    target_files = file_change[language.isin(languages)].copy()

    absent_files = target_files[target_files["hash_norm"].isin(absent)]
    rows = absent_files.merge(
        method_change[method_change["file_change_id"].isin(absent_files["file_change_id"])][
            ["file_change_id", "before_flag"]
        ],
        on="file_change_id",
        how="inner",
    )

    def count(frame, mask=None):
        frame = frame if mask is None else frame[mask]
        return frame.groupby("hash_norm").size()

    details = pd.DataFrame({"commit": absent})
    details["file_change_rows"] = details["commit"].map(count(file_change)).fillna(0).astype(int)
    details["target_file_rows"] = details["commit"].map(count(target_files)).fillna(0).astype(int)
    details["method_change_rows"] = details["commit"].map(count(rows)).fillna(0).astype(int)
    details["before_change_true"] = (
        details["commit"].map(count(rows, rows["before_flag"].eq("true"))).fillna(0).astype(int)
    )
    details["before_change_false"] = (
        details["commit"].map(count(rows, rows["before_flag"].eq("false"))).fillna(0).astype(int)
    )
    details["before_change_unknown"] = (
        details["commit"]
        .map(count(rows, ~rows["before_flag"].isin(["true", "false"])))
        .fillna(0)
        .astype(int)
    )
    details["cve_links"] = (
        details["commit"].map(fixes.groupby("hash_norm")["cve_id"].nunique()).fillna(0).astype(int)
    )
    if line_cols:
        lines_by_commit = target_files.groupby("hash_norm")[line_cols].sum()
        for col in line_cols:
            details[col] = details["commit"].map(lines_by_commit[col])
    details["diagnosis"] = details.apply(diagnose, axis=1)

    repo_of = (
        fixes.drop_duplicates("hash_norm").set_index("hash_norm")["repo_url"]
        if "repo_url" in fixes.columns
        else pd.Series(dtype="object")
    )
    rng = random.Random(SEED)

    # ----- summary of observed diagnoses
    grouped = details.groupby("diagnosis")
    summary = grouped.agg(
        commits=("commit", "nunique"),
        cve_links=("cve_links", "sum"),
        median_function_rows=("method_change_rows", "median"),
    ).reset_index()
    summary["share"] = (100 * summary["commits"] / max(len(details), 1)).map(lambda x: f"{x:.1f}%")
    columns = ["diagnosis", "commits", "share", "cve_links", "median_function_rows"]
    if "num_lines_deleted" in details.columns:
        summary["zero_deleted_lines"] = summary["diagnosis"].map(
            grouped["num_lines_deleted"].apply(zero_deleted)
        )
        columns.append("zero_deleted_lines")
    summary = summary.sort_values(["commits", "diagnosis"], ascending=[False, True])[columns]

    md = [
        f"# CVEfixes absent-commit diagnostics: {name}",
        "",
        f"Generated by `scripts/data_audit/check_cvefixes_absent_commits.py {name}`.",
        "",
        "## Coverage overview",
        "",
        f"- Target languages (from file_change.csv): {sorted(languages)}",
        f"- Unique valid commits in fixes.csv: {len(fix_hashes):,}",
        f"- Represented in the function-level dataset: {len(present):,}",
        f"- Absent from the function-level dataset: {len(absent):,} "
        f"({100 * len(absent) / max(len(fix_hashes), 1):.1f}%)",
        f"- Dataset commits not found in fixes.csv: {len(dataset_hashes - fix_hashes):,}",
        "",
        "A diagnosis describes the evidence in the raw tables. It is not proof of a loader bug.",
        "",
        "## Observed diagnoses",
        "",
    ]
    md += markdown_table(summary)
    if "num_lines_deleted" in details.columns:
        baseline = (
            target_files.groupby("hash_norm")["num_lines_deleted"].sum().reindex(sorted(present))
        )
        md += [
            f"- Baseline, commits that reached the dataset, share with 0 deleted lines: "
            f"{zero_deleted(baseline)}",
            "",
        ]

    # ----- did the function exist before? (only where new-version rows exist alone)
    new_only = details.loc[
        (details["before_change_true"] == 0) & (details["before_change_false"] > 0), "commit"
    ].tolist()
    if new_only and "code_before" in fc_header and "name" in mc_header:
        md += existed_before(
            raw, target_files, set(new_only), method_change, examples, rng, repo_of
        )

    # ----- random examples per diagnosis
    md += [f"## Random examples ({examples} per diagnosis, seed {SEED})", ""]
    example_cols = ["method_change_rows", "before_change_true", "before_change_false"] + line_cols
    for diagnosis, group in details.groupby("diagnosis"):
        picked = group.sample(n=min(examples, len(group)), random_state=SEED).sort_values("commit")
        view = picked[["commit"] + example_cols].copy()
        view["commit"] = [commit_url(repo_of.get(c), c) for c in view["commit"]]
        md += [f"### {diagnosis}", ""] + markdown_table(view)

    if full:
        md += ["## Per-commit evidence (all absent commits)", ""]
        full_cols = [
            "commit",
            "diagnosis",
            "cve_links",
            "file_change_rows",
            "target_file_rows",
            "method_change_rows",
            "before_change_true",
            "before_change_false",
            "before_change_unknown",
        ] + line_cols
        md += markdown_table(details[full_cols])

    md += [
        "## Notes",
        "",
        "- Function counts are rows in `method_change.csv` joined to target-language file changes; "
        "they are not deduplicated functions.",
        "- `before_change=True` rows are the candidates for vulnerable samples; commits that have "
        "none cannot produce one.",
    ]

    DOCS.mkdir(parents=True, exist_ok=True)
    out = DOCS / f"{name}_absent_commits.md"
    out.write_text("\n".join(md).rstrip() + "\n", encoding="utf-8")

    print(f"== {name}: {len(absent):,} of {len(fix_hashes):,} commits absent")
    print(summary.to_string(index=False))
    print(f"Report written to {out.relative_to(ROOT)}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "names", nargs="*", help="folders under data/raw (default: all that qualify)"
    )
    parser.add_argument(
        "--languages", help="comma-separated, e.g. c,c++ (default: from file_change.csv)"
    )
    parser.add_argument("--examples", type=int, default=5, help="random examples per diagnosis")
    parser.add_argument("--full", action="store_true", help="also list every absent commit")
    args = parser.parse_args()

    names = [resolve_name(n) for n in args.names] if args.names else discover()
    if not names:
        raise SystemExit(
            "No folder in data/raw has fixes.csv + file_change.csv + method_change.csv"
        )
    languages = {x.strip().lower() for x in args.languages.split(",")} if args.languages else None
    for name in names:
        run(name, languages, args.examples, args.full)


if __name__ == "__main__":
    main()
