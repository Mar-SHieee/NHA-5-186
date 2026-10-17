"""Project-name normalization and audit utilities for SHIELD.

Run from the repository root:
    python -m shield_core.datasets.project_normalization
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "interim"
DOCS_DIR = REPO_ROOT / "docs"


# ---------------------------------------------------------------------
# Verified aliases
# ---------------------------------------------------------------------
# Map aliases to a canonical project name.
# Add aliases only after verifying that they refer to the same project.
PROJECT_ALIASES = {
    "linux": "torvalds/linux",
    "torvalds/linux": "torvalds/linux",
    "ffmpeg": "ffmpeg",
    "android": "android",
    "keepalived": "acassen/keepalived",
    "acassen/keepalived": "acassen/keepalived",
    "mujs": "ccxvii/mujs",
    "ccxvii/mujs": "ccxvii/mujs",
    "radare2": "radareorg/radare2",
    "radareorg/radare2": "radareorg/radare2",
    "php": "php/php-src",
    "php/php-src": "php/php-src",
    "yara": "virustotal/yara",
    "virustotal/yara": "virustotal/yara",
    "cjson": "davegamble/cjson",
    "davegamble/cjson": "davegamble/cjson",
}


# ---------------------------------------------------------------------
# 1. Normalize a single project name
# ---------------------------------------------------------------------
def normalize_project_name(project: object) -> object:
    """Normalize a project name without guessing unknown aliases."""
    if pd.isna(project):
        return pd.NA

    name = str(project).strip().lower()
    name = name.replace("\\", "/")
    name = re.sub(r"\s+", "", name)
    name = name.rstrip("/")

    if not name:
        return pd.NA

    return PROJECT_ALIASES.get(name, name)


# ---------------------------------------------------------------------
# 2. Add normalized project column
# ---------------------------------------------------------------------
def add_normalized_project_column(
    df: pd.DataFrame,
    project_col: str = "project",
    output_col: str = "project_normalized",
) -> pd.DataFrame:
    """Return a copy with a normalized project column."""
    if project_col not in df.columns:
        raise KeyError(f"Missing required column: {project_col}")

    result = df.copy()
    result[output_col] = result[project_col].map(normalize_project_name)
    return result


# ---------------------------------------------------------------------
# 3. Find commits associated with multiple raw project names
# ---------------------------------------------------------------------
def find_shared_commit_project_names(
    df: pd.DataFrame,
    commit_col: str = "commit",
    project_col: str = "project",
) -> pd.DataFrame:
    """Return commit/project combinations for shared commits."""
    required = {commit_col, project_col}
    missing = required - set(df.columns)

    if missing:
        raise KeyError(f"Missing required columns: {sorted(missing)}")

    data = df[[commit_col, project_col]].copy()

    for col in [commit_col, project_col]:
        data[col] = data[col].astype("string").str.strip()

    data = data.dropna(subset=[commit_col, project_col])
    data = data[data[commit_col].ne("") & data[project_col].ne("")]

    details = data.groupby([commit_col, project_col]).size().reset_index(name="rows")

    shared = details[details.groupby(commit_col)[project_col].transform("nunique").gt(1)].copy()

    return shared.sort_values([commit_col, project_col])


# ---------------------------------------------------------------------
# 4. Suggest possible aliases using shared commits
# ---------------------------------------------------------------------
def build_project_alias_candidates(
    df: pd.DataFrame,
    commit_col: str = "commit",
    project_col: str = "project",
) -> pd.DataFrame:
    """Suggest name pairs sharing commits; does not merge them."""
    shared = find_shared_commit_project_names(
        df,
        commit_col=commit_col,
        project_col=project_col,
    )

    columns = ["project_a", "project_b", "shared_commits"]

    if shared.empty:
        return pd.DataFrame(columns=columns)

    pair_counts: dict[tuple[str, str], int] = defaultdict(int)

    for _, group in shared.groupby(commit_col):
        names = sorted(group[project_col].unique())

        for i, name_a in enumerate(names):
            for name_b in names[i + 1 :]:
                pair_counts[(name_a, name_b)] += 1

    rows = [
        {
            "project_a": name_a,
            "project_b": name_b,
            "shared_commits": count,
        }
        for (name_a, name_b), count in pair_counts.items()
    ]

    return pd.DataFrame(rows, columns=columns).sort_values(
        "shared_commits",
        ascending=False,
    )


# ---------------------------------------------------------------------
# 5. Build mapping and groups of names that normalize identically
# ---------------------------------------------------------------------
def build_project_name_reports(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return raw-to-normalized mapping and merged-name groups."""
    normalized = add_normalized_project_column(df)

    mapping = (
        normalized[["project", "project_normalized"]]
        .drop_duplicates()
        .sort_values(
            ["project_normalized", "project"],
            na_position="last",
        )
    )

    groups = (
        mapping.dropna(subset=["project_normalized"])
        .groupby("project_normalized")["project"]
        .agg(lambda names: sorted(set(names)))
        .reset_index(name="original_names")
    )

    groups["num_original_names"] = groups["original_names"].map(len)

    groups = groups[groups["num_original_names"] > 1].copy()

    return mapping, groups


# ---------------------------------------------------------------------
# 6. Load datasets
# ---------------------------------------------------------------------
def load_datasets() -> pd.DataFrame:
    """Load the deduplicated Big-Vul and MegaVul datasets."""
    paths = {
        "Big-Vul": DATA_DIR / "bigvul_deduped.parquet",
        "MegaVul": DATA_DIR / "megavul_deduped.parquet",
    }

    frames = []

    for dataset_name, path in paths.items():
        if not path.exists():
            raise FileNotFoundError(f"Dataset not found: {path}")

        frame = pd.read_parquet(path)

        if "project" not in frame.columns:
            raise KeyError(f"Missing 'project' column in {path}")

        if "commit" not in frame.columns:
            raise KeyError(f"Missing 'commit' column in {path}")

        frame["dataset"] = dataset_name
        frames.append(frame)

    return pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    )


def build_alias_review_report(
    df: pd.DataFrame,
    commit_col: str = "commit",
    project_col: str = "project",
) -> pd.DataFrame:
    """Build an evidence report for reviewing possible project aliases."""
    required = {commit_col, project_col}
    missing = required - set(df.columns)
    if missing:
        raise KeyError(f"Missing required columns: {sorted(missing)}")

    data = df[[commit_col, project_col]].copy()
    data[commit_col] = data[commit_col].astype("string").str.strip()
    data[project_col] = data[project_col].astype("string").str.strip()

    data = data.dropna(subset=[commit_col, project_col])
    data = data[data[commit_col].ne("") & data[project_col].ne("")].drop_duplicates(
        [commit_col, project_col]
    )

    project_commits = {
        project: set(group[commit_col]) for project, group in data.groupby(project_col)
    }

    candidates = build_project_alias_candidates(
        data,
        commit_col=commit_col,
        project_col=project_col,
    )

    rows = []
    for row in candidates.itertuples(index=False):
        project_a = row.project_a
        project_b = row.project_b
        shared = row.shared_commits

        commits_a = project_commits[project_a]
        commits_b = project_commits[project_b]

        rows.append(
            {
                "project_a": project_a,
                "project_b": project_b,
                "shared_commits": shared,
                "commits_a": len(commits_a),
                "commits_b": len(commits_b),
                "overlap_pct_a": round(100 * shared / len(commits_a), 2),
                "overlap_pct_b": round(100 * shared / len(commits_b), 2),
                "review_status": "needs_review",
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "project_a",
            "project_b",
            "shared_commits",
            "commits_a",
            "commits_b",
            "overlap_pct_a",
            "overlap_pct_b",
            "review_status",
        ],
    ).sort_values("shared_commits", ascending=False)


# ---------------------------------------------------------------------
# 7. Run the audit and save reports
# ---------------------------------------------------------------------
def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    df = load_datasets()

    print(f"Total rows: {len(df):,}")
    print(f"Original project names: {df['project'].nunique():,}")

    # Normalize names for audit.
    normalized_df = add_normalized_project_column(df)

    print(f"Normalized project names: {normalized_df['project_normalized'].nunique():,}")

    # Raw-to-normalized mapping.
    mapping, groups = build_project_name_reports(df)

    mapping.to_csv(
        DOCS_DIR / "project_name_mapping.csv",
        index=False,
    )

    groups.to_csv(
        DOCS_DIR / "normalized_name_groups.csv",
        index=False,
    )

    print("\n--- Names mapped to the same normalized name ---")
    print(groups.head(30).to_string(index=False))

    # Shared commits.
    shared = find_shared_commit_project_names(df)

    shared.to_csv(
        DOCS_DIR / "shared_commit_projects.csv",
        index=False,
    )

    print("\n--- Shared commit report ---")
    print(f"Shared commit hashes: {shared['commit'].nunique():,}")

    # Alias candidates.
    candidates = build_project_alias_candidates(df)

    candidates.to_csv(
        DOCS_DIR / "project_alias_candidates.csv",
        index=False,
    )

    review_report = build_alias_review_report(df)
    review_path = DOCS_DIR / "project_alias_review.csv"
    review_report.to_csv(review_path, index=False)

    print(f"\nSaved alias review report: {review_path}")
    print(review_report.head(30).to_string(index=False))

    print("\n--- Top alias candidates ---")
    if candidates.empty:
        print("No candidates found.")
    else:
        print(candidates.head(30).to_string(index=False))

    # Save normalized copies without modifying the originals.
    for dataset_name, frame in df.groupby("dataset"):
        normalized_frame = add_normalized_project_column(frame)

        output_name = (
            "bigvul_normalized.parquet"
            if dataset_name == "Big-Vul"
            else "megavul_normalized.parquet"
        )

        output_path = DATA_DIR / output_name
        normalized_frame.to_parquet(output_path, index=False)

        print(f"Saved: {output_path}")

    print("\nProject normalization audit completed.")
    print(f"Reports directory: {DOCS_DIR}")


if __name__ == "__main__":
    main()
