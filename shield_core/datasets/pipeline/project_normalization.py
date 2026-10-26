"""Project-name normalization and audit utilities for SHIELD.

The audit runs on every deduped dataset (`data/interim/*_deduped.parquet`).

Run from the repository root:
    python -m shield_core.datasets.pipeline.project_normalization
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

from shield_core.paths import DOCS_PROJECT_NAMES_DIR, REPO_ROOT

# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------

DATA_DIR = REPO_ROOT / "data" / "interim"
DOCS_DIR = DOCS_PROJECT_NAMES_DIR


# ---------------------------------------------------------------------
# Aliases: manual overrides + aliases learned from the data
# ---------------------------------------------------------------------
# MANUAL_ALIASES is only for human-verified exceptions the data cannot reveal.
# Everything else is discovered by `learn_aliases` (see below) and stored in
# docs/datasets/project_names/project_aliases.json, which `normalize_project_name` reads
# automatically.
MANUAL_ALIASES: dict[str, str] = {
    "php": "php/php-src",
}
ALIASES_PATH = DOCS_DIR / "project_aliases.json"

_GITHUB_PREFIX = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/")
_LEARNED: dict[str, str] | None = None


def reload_learned_aliases(path: Path = ALIASES_PATH) -> dict[str, str]:
    """(Re)load the learned alias map from disk; empty if the file does not exist yet."""
    global _LEARNED
    try:
        _LEARNED = dict(json.loads(Path(path).read_text(encoding="utf-8"))["aliases"])
    except (OSError, ValueError, KeyError):
        _LEARNED = {}
    return _LEARNED


def _clean_name(project: object) -> str | None:
    """Purely syntactic cleanup: case, spaces, slashes, github URL prefix, '.git' suffix."""
    if project is None or project is pd.NA or pd.isna(project):
        return None
    name = str(project).strip().lower().replace("\\", "/")
    name = re.sub(r"\s+", "", name)
    name = _GITHUB_PREFIX.sub("", name).rstrip("/")
    if name.endswith(".git"):
        name = name[:-4]
    return name or None


# ---------------------------------------------------------------------
# 1. Normalize a single project name
# ---------------------------------------------------------------------
def normalize_project_name(project: object) -> object:
    """Canonical project name: syntactic cleanup, manual overrides, then learned aliases."""
    name = _clean_name(project)
    if name is None:
        return pd.NA
    name = MANUAL_ALIASES.get(name, name)
    learned = _LEARNED if _LEARNED is not None else reload_learned_aliases()
    return learned.get(name, name)


# ---------------------------------------------------------------------
# 1b. Learn aliases from the data (no hard-coded names)
# ---------------------------------------------------------------------
def learn_aliases(
    df: pd.DataFrame,
    project_col: str = "project",
    commit_col: str = "commit",
) -> tuple[dict[str, str], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Find names that refer to the same project, using evidence from all datasets.

    Rules (merged automatically):
      shared_commit      two names carry the same commit hash (first 12 hex chars)
      bare_name_unique   a bare name ('ffmpeg') equals the repo part of exactly ONE
                         'owner/repo' name ('ffmpeg/ffmpeg')
    Reported but NOT merged: bare names matching several owners, and the same repo name
    under different owners (possible forks).

    Returns (aliases {name: canonical}, evidence, ambiguous, same_repo_other_owner).
    The canonical name prefers 'owner/repo' form, then the most rows.
    """
    names = df[project_col].map(_clean_name)
    rows = names.value_counts()
    all_names = list(rows.index)
    parent = {n: n for n in all_names}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    evidence: list[dict] = []

    # rule 1: shared commit hash
    c = df[commit_col].astype("string").str.strip().str.lower()
    key = c.where(c.str.fullmatch(r"[0-9a-f]{12,40}", na=False)).str[:12]
    pairs = pd.DataFrame({"n": names, "k": key}).dropna().drop_duplicates()
    multi = pairs.groupby("k")["n"].agg(lambda s: sorted(set(s)))
    shared: dict[tuple[str, str], int] = defaultdict(int)
    for lst in multi[multi.map(len) > 1]:
        for i, name_a in enumerate(lst):
            for name_b in lst[i + 1 :]:
                shared[(name_a, name_b)] += 1
    for (name_a, name_b), k in shared.items():
        union(name_a, name_b)
        evidence.append(
            {"name_a": name_a, "name_b": name_b, "rule": "shared_commit", "detail": f"{k} commits"}
        )

    # rule 2: bare name == repo part of exactly one owner/repo name
    by_repo: dict[str, set[str]] = defaultdict(set)
    for n in all_names:
        if "/" in n:
            by_repo[n.rsplit("/", 1)[-1]].add(n)
    ambiguous = []
    for n in all_names:
        if "/" in n:
            continue
        cands = by_repo.get(n, set())
        if len(cands) == 1:
            (q,) = cands
            if find(n) != find(q):
                union(n, q)
                evidence.append(
                    {"name_a": n, "name_b": q, "rule": "bare_name_unique", "detail": "unique repo"}
                )
        elif len(cands) > 1 and not any(find(q) == find(n) for q in cands):
            ambiguous.append(
                {"name": n, "rows": int(rows[n]), "candidates": "; ".join(sorted(cands))}
            )

    same_repo = [
        {"repo": repo, "names": "; ".join(sorted(s))} for repo, s in by_repo.items() if len(s) > 1
    ]

    # canonical name per connected component
    comps: dict[str, list[str]] = defaultdict(list)
    for n in all_names:
        comps[find(n)].append(n)
    canonical_of: dict[str, str] = {}
    for members in comps.values():
        rep = sorted(members, key=lambda n: (0 if "/" in n else 1, -int(rows[n]), n))[0]
        for n in members:
            canonical_of[n] = rep
    aliases = {n: rep for n, rep in canonical_of.items() if n != rep}

    ev = pd.DataFrame(evidence, columns=["name_a", "name_b", "rule", "detail"])
    ev["canonical"] = ev["name_a"].map(canonical_of)
    return (
        aliases,
        ev,
        pd.DataFrame(ambiguous, columns=["name", "rows", "candidates"]),
        pd.DataFrame(same_repo, columns=["repo", "names"]),
    )


def save_aliases(
    aliases: dict[str, str], path: Path = ALIASES_PATH, sources: list[str] | None = None
) -> None:
    """Write the learned alias map and make `normalize_project_name` use it right away."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_by": "project_normalization.learn_aliases",
        "rules": ["shared_commit", "bare_name_unique"],
        "datasets": sources or [],
        "aliases": dict(sorted(aliases.items())),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    reload_learned_aliases(path)


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
DEDUPED_GLOB = "*_deduped.parquet"  # one file per dataset, written by dedupe.py


def dataset_name(path: Path) -> str:
    """'megavul_deduped.parquet' -> 'megavul'."""
    return path.name[: -len("_deduped.parquet")]


def load_datasets(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Load every deduplicated dataset (`*_deduped.parquet`) found in `data_dir`.

    Adds a `dataset` column taken from the file name, so new datasets are picked up
    without editing this file.
    """
    paths = sorted(Path(data_dir).glob(DEDUPED_GLOB))
    if not paths:
        raise FileNotFoundError(f"No '{DEDUPED_GLOB}' files found in {data_dir}")

    frames = []

    for path in paths:
        frame = pd.read_parquet(path)

        if "project" not in frame.columns:
            raise KeyError(f"Missing 'project' column in {path}")

        if "commit" not in frame.columns:
            raise KeyError(f"Missing 'commit' column in {path}")

        frame["dataset"] = dataset_name(path)
        print(f"  loaded {path.name}: {len(frame):,} rows")
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

    # Learn aliases from all datasets first, so every report below uses them.
    aliases, evidence, ambiguous, same_repo = learn_aliases(df)
    save_aliases(aliases, sources=sorted(df["dataset"].unique()))
    evidence.to_csv(DOCS_DIR / "project_alias_evidence.csv", index=False)
    ambiguous.to_csv(DOCS_DIR / "project_alias_ambiguous.csv", index=False)
    same_repo.to_csv(DOCS_DIR / "project_same_repo_other_owner.csv", index=False)
    print(f"Learned {len(aliases):,} aliases -> {ALIASES_PATH}")
    print(f"  ambiguous bare names (not merged): {len(ambiguous):,}")
    print(f"  same repo name under different owners (not merged): {len(same_repo):,}")

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
    for dataset_name_, frame in df.groupby("dataset"):
        normalized_frame = add_normalized_project_column(frame)

        output_name = f"{dataset_name_}_normalized.parquet"

        output_path = DATA_DIR / output_name
        normalized_frame.to_parquet(output_path, index=False)

        print(f"Saved: {output_path}")

    print("\nProject normalization audit completed.")
    print(f"Reports directory: {DOCS_DIR}")


if __name__ == "__main__":
    main()
