"""Explore the CVEfixes C/C++ interim data and write a Markdown report.

Run from the repository root:
    python scripts/data_audit/explore_cvefixes_cpp.py
"""

from collections import Counter

import numpy as np
import pandas as pd

from shield_core.paths import DOCS_EXPLORATION_DIR, REPO_ROOT

ROOT = REPO_ROOT
DATA = ROOT / "data" / "interim"
DOCS = DOCS_EXPLORATION_DIR

NAME = "cvefixes_cpp"
FUNCTIONS_FILE = DATA / f"{NAME}.parquet"
MAPPING_FILE = DATA / f"{NAME}_commit_cve_mapping.parquet"
REPORT_FILE = DOCS / f"{NAME}_exploration.md"


def as_list(value):
    """Normalize list-like cells, including NumPy arrays."""
    if value is None:
        return []

    if isinstance(value, (list, tuple, set, np.ndarray)):
        result = []
        for item in value:
            if item is None:
                continue
            try:
                if pd.isna(item):
                    continue
            except (TypeError, ValueError):
                pass

            text = str(item).strip()
            if text:
                result.append(text)

        return result

    try:
        if pd.isna(value):
            return []
    except (TypeError, ValueError):
        pass

    text = str(value).strip()
    return [text] if text else []


def count_values(series):
    """Count distinct values across list-like cells."""
    counts = Counter()

    for value in series:
        counts.update(set(as_list(value)))

    return counts


def has_values(value):
    return len(as_list(value)) > 0


def normalize_for_duplicates(value):
    """Convert arrays and collections into comparable values."""
    if isinstance(value, np.ndarray):
        return tuple(normalize_for_duplicates(v) for v in value.tolist())

    if isinstance(value, (list, tuple)):
        return tuple(normalize_for_duplicates(v) for v in value)

    if isinstance(value, set):
        return tuple(sorted(str(v) for v in value))

    if isinstance(value, dict):
        return tuple(sorted((k, normalize_for_duplicates(v)) for k, v in value.items()))

    return value


class Report:
    """Collect Markdown lines and write them to a file."""

    def __init__(self):
        self.lines = []

    def h(self, level, title):
        self.lines += ["", f"{'#' * level} {title}", ""]

    def p(self, text):
        self.lines.append(text)

    def bullet(self, text):
        self.lines.append(f"- {text}")

    def table(self, df):
        if df.empty:
            self.p("_No values found._")
            return

        df = df.astype(str)
        self.lines.append("| " + " | ".join(df.columns) + " |")
        self.lines.append("| " + " | ".join("---" for _ in df.columns) + " |")

        for row in df.itertuples(index=False, name=None):
            cells = [cell.replace("|", "\\|").replace("\n", " ") for cell in row]
            self.lines.append("| " + " | ".join(cells) + " |")

        self.lines.append("")

    def top(self, title, counter, label, n=15):
        self.h(3, title)
        self.table(pd.DataFrame(counter.most_common(n), columns=[label, "count"]))

    def save(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(self.lines).strip() + "\n",
            encoding="utf-8",
        )


def section_shapes(r, df, mapping):
    r.h(2, "1. File shapes")
    r.bullet(f"Function rows: {len(df):,}")
    r.bullet(f"Function columns: `{list(df.columns)}`")
    r.bullet(f"Commit-CVE mapping rows: {len(mapping):,}")
    r.bullet(f"Mapping columns: `{list(mapping.columns)}`")

    missing = [c for c in df.columns if df[c].isna().all()]
    r.bullet(f"Columns entirely null: `{missing}`")


def section_counts(r, df):
    r.h(2, "2. Function and label counts")

    if "label" in df.columns:
        counts = df["label"].value_counts(dropna=False).sort_index()
        r.table(counts.rename_axis("label").reset_index(name="rows"))

        for label, name in [(1, "vulnerable"), (0, "safe")]:
            r.bullet(
                f"{name.capitalize()} rows (label={label}): {int((df['label'] == label).sum()):,}"
            )

    commit_col = next(
        (c for c in ["commit", "hash", "commit_hash"] if c in df.columns),
        None,
    )

    if commit_col:
        r.bullet(f"Unique commits (`{commit_col}`): {df[commit_col].nunique(dropna=True):,}")

    if "project" in df.columns:
        r.bullet(f"Unique projects: {df['project'].nunique(dropna=True):,}")

    if "language" in df.columns:
        r.h(3, "Rows by language")
        r.table(
            df["language"]
            .value_counts(dropna=False)
            .rename_axis("language")
            .reset_index(name="rows")
        )

    if "code" in df.columns:
        r.bullet(f"Unique code strings: {df['code'].nunique(dropna=True):,}")
        r.bullet(
            f"Repeated code rows (excluding first occurrence): {df['code'].duplicated().sum():,}"
        )

        normalized = df.map(normalize_for_duplicates)
        r.bullet(
            "Exact duplicate rows across all columns "
            f"(excluding first occurrence): {normalized.duplicated().sum():,}"
        )


def section_coverage(r, df):
    r.h(2, "3. Function-level CVE / CWE coverage")

    cve_counts = count_values(df["cve"]) if "cve" in df.columns else Counter()
    cwe_counts = count_values(df["cwe"]) if "cwe" in df.columns else Counter()

    r.bullet(f"Distinct CVEs in function rows: {len(cve_counts):,}")
    r.bullet(f"Distinct CWEs in function rows: {len(cwe_counts):,}")

    if "cve" in df.columns:
        r.bullet(f"Rows with at least one CVE: {sum(has_values(v) for v in df['cve']):,}")

    if "cwe" in df.columns:
        r.bullet(f"Rows with at least one CWE: {sum(has_values(v) for v in df['cwe']):,}")

    r.top("Most common CVEs", cve_counts, "cve")
    r.top("Most common CWEs", cwe_counts, "cwe")

    if "label" in df.columns:
        rows = []

        for label, name in [(1, "vulnerable"), (0, "safe")]:
            sub = df[df["label"] == label]
            rows.append(
                {
                    "group": name,
                    "rows": len(sub),
                    "with_cve": (sum(has_values(v) for v in sub["cve"]) if "cve" in sub else "-"),
                    "with_cwe": (sum(has_values(v) for v in sub["cwe"]) if "cwe" in sub else "-"),
                }
            )

        r.h(3, "CVE / CWE coverage by label")
        r.table(pd.DataFrame(rows))

        safe = df[df["label"] == 0]
        r.h(3, "Safe-row metadata checks")

        for col in ("cve", "cwe"):
            if col in safe.columns:
                count = sum(has_values(v) for v in safe[col])
                r.bullet(f"Safe rows with non-empty {col}: {count:,}")


def section_mapping(r, mapping):
    r.h(2, "4. Commit-CVE mapping")

    r.h(3, "First rows")
    r.table(mapping.head(10))

    commit_col = next(
        (c for c in ["commit", "hash", "commit_hash"] if c in mapping.columns),
        None,
    )
    cve_col = next(
        (c for c in ["cve", "cve_id", "cve_name"] if c in mapping.columns),
        None,
    )

    if not (commit_col and cve_col):
        r.p("Could not infer mapping columns. Expected a commit column and a CVE column.")
        return

    links = mapping[[commit_col, cve_col]].dropna().astype(str)
    links = links.apply(lambda col: col.str.strip())
    links = links[(links[commit_col] != "") & (links[cve_col] != "")].drop_duplicates()

    cves_per_commit = links.groupby(commit_col)[cve_col].nunique()
    commits_per_cve = links.groupby(cve_col)[commit_col].nunique()

    r.h(3, "Mapping summary")
    r.bullet(f"Distinct commit-CVE links: {len(links):,}")
    r.bullet(f"Distinct commits: {links[commit_col].nunique():,}")
    r.bullet(f"Distinct CVEs: {links[cve_col].nunique():,}")
    r.bullet(f"Commits linked to multiple CVEs: {int((cves_per_commit > 1).sum()):,}")
    r.bullet(f"CVEs linked to multiple commits: {int((commits_per_cve > 1).sum()):,}")
    r.bullet(
        "Maximum CVEs linked to one commit: "
        f"{int(cves_per_commit.max()) if len(cves_per_commit) else 0}"
    )
    r.bullet(
        "Maximum commits linked to one CVE: "
        f"{int(commits_per_cve.max()) if len(commits_per_cve) else 0}"
    )

    r.bullet(f"Duplicate commit-CVE links in the raw mapping: {mapping.duplicated().sum():,}")

    r.h(3, "Top CVEs by number of linked commits")
    r.table(commits_per_cve.sort_values(ascending=False).head(15).rename("commits").reset_index())

    r.h(3, "Top commits by number of linked CVEs")
    r.table(cves_per_commit.sort_values(ascending=False).head(15).rename("cves").reset_index())

    multi = cves_per_commit[cves_per_commit > 1].sort_values(ascending=False).head(10)

    r.h(3, "Examples of commits linked to multiple CVEs")

    if multi.empty:
        r.p("None.")
    else:
        rows = [
            {
                "commit": commit,
                "number_of_cves": count,
                "cves": ", ".join(sorted(links.loc[links[commit_col] == commit, cve_col].unique())),
            }
            for commit, count in multi.items()
        ]
        r.table(pd.DataFrame(rows))


def section_consistency(r, df, mapping):
    r.h(2, "5. Consistency checks")

    if "commit" in df.columns and "commit" in mapping.columns:
        dataset_commits = set(df["commit"].dropna().astype(str))
        mapping_commits = set(mapping["commit"].dropna().astype(str))

        r.bullet(f"Dataset commits: {len(dataset_commits):,}")
        r.bullet(f"Mapping commits: {len(mapping_commits):,}")
        r.bullet(f"Dataset commits absent from mapping: {len(dataset_commits - mapping_commits):,}")
        r.bullet(f"Mapping commits absent from dataset: {len(mapping_commits - dataset_commits):,}")

    if "cve" in mapping.columns:
        empty_cves = sum(not has_values(v) for v in mapping["cve"])
        r.bullet(f"Mapping rows with empty CVE: {empty_cves:,}")

    if "commit" in mapping.columns and "cve" in mapping.columns:
        links = mapping[["commit", "cve"]].dropna().astype(str)
        links = links.apply(lambda col: col.str.strip())
        links = links[(links["commit"] != "") & (links["cve"] != "")]
        r.bullet(f"Repeated commit-CVE pairs: {links.duplicated().sum():,}")


def section_samples(r, df):
    r.h(2, "6. Sample records")

    columns = [
        c
        for c in [
            "label",
            "language",
            "project",
            "commit",
            "cve",
            "cwe",
            "date",
        ]
        if c in df.columns
    ]

    sample = df[columns].head(10).copy()

    for col in ("cve", "cwe"):
        if col in sample.columns:
            sample[col] = sample[col].map(lambda value: ", ".join(as_list(value)))

    r.table(sample)


def main():
    for path in (FUNCTIONS_FILE, MAPPING_FILE):
        if not path.exists():
            raise FileNotFoundError(f"Missing file: {path}")

    df = pd.read_parquet(FUNCTIONS_FILE)
    mapping = pd.read_parquet(MAPPING_FILE)

    r = Report()
    r.p("# CVEfixes C/C++ dataset exploration")
    r.p(
        f"Generated by `scripts/data_audit/explore_cvefixes_cpp.py` from "
        f"`{FUNCTIONS_FILE.name}` and `{MAPPING_FILE.name}`."
    )

    section_shapes(r, df, mapping)
    section_counts(r, df)
    section_coverage(r, df)
    section_mapping(r, mapping)
    section_consistency(r, df, mapping)
    section_samples(r, df)

    r.save(REPORT_FILE)
    print(f"Report written to {REPORT_FILE}")


if __name__ == "__main__":
    main()
