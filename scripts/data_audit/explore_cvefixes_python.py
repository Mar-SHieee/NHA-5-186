"""Explore the CVEfixes Python interim data and write the result to docs/ as Markdown.

Run from the repository root:
    python scripts/explore_cvefixes.py
"""

from collections import Counter

import numpy as np
import pandas as pd

from shield_core.paths import DOCS_EXPLORATION_DIR, REPO_ROOT

ROOT = REPO_ROOT
DATA = ROOT / "data" / "interim"
DOCS = DOCS_EXPLORATION_DIR

NAME = "cvefixes_python"
FUNCTIONS_FILE = DATA / f"{NAME}.parquet"
MAPPING_FILE = DATA / f"{NAME}_commit_cve_mapping.parquet"
REPORT_FILE = DOCS / f"{NAME}_exploration.md"


def as_list(value):
    """Normalize list-like cells, including NumPy arrays."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set, np.ndarray)):
        return [
            str(i).strip() for i in value if i is not None and not pd.isna(i) and str(i).strip()
        ]
    if pd.isna(value):
        return []
    text = str(value).strip()
    return [text] if text else []


def count_values(series):
    counts = Counter()
    for value in series:
        counts.update(set(as_list(value)))
    return counts


class Report:
    """Collects Markdown lines and writes them to one file."""

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
        for row in df.itertuples(index=False):
            self.lines.append("| " + " | ".join(c.replace("|", "\\|") for c in row) + " |")
        self.lines.append("")

    def top(self, title, counter, label, n=15):
        self.h(3, title)
        self.table(pd.DataFrame(counter.most_common(n), columns=[label, "rows"]))

    def save(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.lines).strip() + "\n", encoding="utf-8")


def section_shapes(r, df, mapping):
    r.h(2, "1. File shapes")
    r.bullet(f"Function rows: {len(df):,}")
    r.bullet(f"Function columns: `{list(df.columns)}`")
    r.bullet(f"Commit-CVE mapping rows: {len(mapping):,}")
    r.bullet(f"Mapping columns: `{list(mapping.columns)}`")


def section_counts(r, df):
    r.h(2, "2. Function / label counts")
    if "label" in df.columns:
        counts = df["label"].value_counts(dropna=False).sort_index()
        r.table(counts.rename_axis("label").reset_index(name="rows"))
    commit_col = next((c for c in ["commit", "hash", "commit_hash"] if c in df.columns), None)
    if commit_col:
        r.bullet(f"Unique commits (`{commit_col}`): {df[commit_col].nunique(dropna=True):,}")
    else:
        r.bullet("No recognized commit column in the function dataset.")
    if "project" in df.columns:
        r.bullet(f"Unique projects: {df['project'].nunique(dropna=True):,}")
    if "code" in df.columns:
        r.bullet(f"Unique code strings: {df['code'].nunique(dropna=True):,}")
        r.bullet(f"Exact duplicate code rows: {df['code'].duplicated().sum():,}")


def section_coverage(r, df):
    r.h(2, "3. Function-level CVE / CWE coverage")
    cve_counts = count_values(df["cve"]) if "cve" in df.columns else Counter()
    cwe_counts = count_values(df["cwe"]) if "cwe" in df.columns else Counter()
    r.bullet(f"Distinct CVEs in function rows: {len(cve_counts):,}")
    r.bullet(f"Distinct CWEs in function rows: {len(cwe_counts):,}")
    if "cve" in df.columns:
        r.bullet(f"Rows with at least one CVE: {sum(bool(as_list(x)) for x in df['cve']):,}")
    if "cwe" in df.columns:
        r.bullet(f"Rows with at least one CWE: {sum(bool(as_list(x)) for x in df['cwe']):,}")
    r.top("Most common CVEs", cve_counts, "cve")
    r.top("Most common CWEs", cwe_counts, "cwe")
    if "label" in df.columns:
        rows = []
        for label, name in [(1, "vulnerable"), (0, "safe")]:
            sub = df[df["label"] == label]
            rows.append(
                {
                    "group": name,
                    "rows": f"{len(sub):,}",
                    "with_cve": f"{sum(bool(as_list(x)) for x in sub['cve']):,}"
                    if "cve" in sub
                    else "-",
                    "with_cwe": f"{sum(bool(as_list(x)) for x in sub['cwe']):,}"
                    if "cwe" in sub
                    else "-",
                }
            )
        r.h(3, "By label")
        r.table(pd.DataFrame(rows))


def section_mapping(r, mapping):
    r.h(2, "4. Commit-CVE mapping")
    r.h(3, "First rows")
    r.table(mapping.head(10))
    commit_col = next((c for c in ["commit", "hash", "commit_hash"] if c in mapping.columns), None)
    cve_col = next((c for c in ["cve", "cve_id", "cve_name"] if c in mapping.columns), None)
    if not (commit_col and cve_col):
        r.p("Could not infer the mapping columns (expected a commit column and a CVE column).")
        return
    links = mapping[[commit_col, cve_col]].dropna().astype(str).apply(lambda s: s.str.strip())
    links = links[(links[commit_col] != "") & (links[cve_col] != "")].drop_duplicates()
    cves_per_commit = links.groupby(commit_col)[cve_col].nunique()
    commits_per_cve = links.groupby(cve_col)[commit_col].nunique()

    r.h(3, "Summary")
    r.bullet(f"Distinct commit-CVE links: {len(links):,}")
    r.bullet(f"Distinct commits: {links[commit_col].nunique():,}")
    r.bullet(f"Distinct CVEs: {links[cve_col].nunique():,}")
    r.bullet(f"Commits linked to multiple CVEs: {int((cves_per_commit > 1).sum()):,}")
    r.bullet(f"CVEs linked to multiple commits: {int((commits_per_cve > 1).sum()):,}")
    r.bullet(f"Max CVEs on one commit: {int(cves_per_commit.max()) if len(cves_per_commit) else 0}")
    r.bullet(f"Max commits on one CVE: {int(commits_per_cve.max()) if len(commits_per_cve) else 0}")

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
                "commit": c,
                "cves": n,
                "ids": ", ".join(sorted(links.loc[links[commit_col] == c, cve_col].unique())),
            }
            for c, n in multi.items()
        ]
        r.table(pd.DataFrame(rows))


def section_samples(r, df):
    r.h(2, "5. Sample records")
    columns = [
        c
        for c in ["label", "language", "project", "commit", "cve", "cwe", "date"]
        if c in df.columns
    ]
    sample = df[columns].head(10).copy()
    for col in ("cve", "cwe"):
        if col in sample:
            sample[col] = sample[col].map(lambda v: ", ".join(as_list(v)))
    r.table(sample)


def main():
    for path in (FUNCTIONS_FILE, MAPPING_FILE):
        if not path.exists():
            raise FileNotFoundError(f"Missing file: {path}")

    df = pd.read_parquet(FUNCTIONS_FILE)
    mapping = pd.read_parquet(MAPPING_FILE)

    r = Report()
    r.p("# CVEfixes Python dataset exploration")
    r.p(
        f"Generated by `scripts/data_audit/explore_cvefixes_python.py` "
        f"from `{FUNCTIONS_FILE.name}` and `{MAPPING_FILE.name}`."
    )
    section_shapes(r, df, mapping)
    section_counts(r, df)
    section_coverage(r, df)
    section_mapping(r, mapping)
    section_samples(r, df)

    r.save(REPORT_FILE)
    print(f"Report written to {REPORT_FILE}")


if __name__ == "__main__":
    main()
