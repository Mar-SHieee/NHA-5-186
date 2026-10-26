"""Project-disjoint, group-aware split: train / val / test / holdout (W2-P1-01, manifest v0.2).

Pipeline
  1. read merged_datasets.parquet (run merge.py first)
  2. optional D39: add patched Python code as label-0 rows (off by default, unchanged)
  3. canonicalize project names (project_normalization.py), then build connected components:
     rows are linked through their (canonical) project AND their commit, so every project
     and every commit lives in exactly one component
  4. assign whole components to splits by greedy largest-first placement + local search,
     minimizing a normalized multilabel-CWE / size / label balance loss
  5. validate (missing, duplicates, group / commit / project leakage, CWE distribution),
     write split files and docs/datasets/audits/dataset_manifest_v0.json

Run:  python -m shield_core.datasets.pipeline.splits [--d39-patched-negatives] [--strict-cwe]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from shield_core.datasets import schema
from shield_core.datasets.pipeline import merge
from shield_core.datasets.pipeline.project_normalization import normalize_project_name
from shield_core.paths import DOCS_AUDITS_DIR, DOCS_PROJECT_NAMES_DIR

SEED = 42
RATIOS = {"train": 0.70, "val": 0.10, "test": 0.10, "holdout": 0.10}
SPLITS = tuple(RATIOS)
HOLDOUT_IDX = SPLITS.index("holdout")
MANIFEST_VERSION = "v0.2"
SPLIT_METHOD = (
    "project-disjoint connected components, greedy + local search (multilabel CWE balance)"
)

# Optimizer settings
REFINE_TOP = 5000  # local search considers the heaviest N components
REFINE_PASSES = 8
FEATURE_WEIGHTS = {"rows": 2.0, "positives": 1.0, "cwe": 1.0}

# CWE reporting
TOL_ABS = 0.05  # |share - target ratio| above this is reported
RATIO_TOL = 0.02  # row-share deviation per split above this is reported

REPO_ROOT = merge.REPO_ROOT
SPLITS_DIR = REPO_ROOT / "data" / "interim" / "splits"
MANIFEST_PATH = DOCS_AUDITS_DIR / "dataset_manifest_v0.json"

_MISSING = {"", "nan", "none", "null", "na", "n/a", "unknown", "<na>"}

LIMITATIONS = [
    (
        "Project names are canonicalized by project_normalization.normalize_project_name "
        "(syntactic cleanup, manual overrides, aliases learned from shared commits and "
        "unique bare names in docs/datasets/project_names/project_aliases.json). "
        "Aliases without such evidence "
        "are not reconciled (see project_name_variants_suspected). "
        "Abbreviated commit hashes are not matched to full ones."
    )
]


class SplitValidationError(RuntimeError):
    pass


# --------------------------------------------------------------------------- names
def _clean(value) -> str | None:
    if value is None or value is pd.NA:
        return None
    text = str(value).strip().lower()
    return None if text in _MISSING else text


def normalize_commit(value) -> str | None:
    return _clean(value)


# The single project canonicalizer used for every split decision (recorded in the manifest).
NORMALIZER_NAME = f"{normalize_project_name.__module__}.{normalize_project_name.__qualname__}"


def canonical_project(value) -> str | None:
    """Canonical project name via normalize_project_name (verified aliases); None if unknown."""
    out = normalize_project_name(value)
    if pd.isna(out):
        return None
    out = str(out)
    return None if out.lower() in _MISSING else out


def _cwe_list(value) -> list[str]:
    """Distinct CWE ids of one row, in order; [] for empty or missing values."""
    if isinstance(value, (list, tuple, np.ndarray)):
        return list(dict.fromkeys(value))
    return []


# --------------------------------------------------------------------------- components
class _UnionFind:
    """Union-find whose root is always the smallest node name (stable component ids)."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, x: str) -> None:
        self.parent.setdefault(x, x)

    def find(self, x: str) -> str:
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def build_group_keys(df: pd.DataFrame, parent_row_id: np.ndarray | None = None) -> pd.DataFrame:
    """Return row_id, project_key, commit_key, group_key, group_kind, parent_row_id per row.

    Nodes are canonical projects ("p:") and commits ("c:"). A row with both links them, so
    projects sharing a commit and commits sharing a project fall into one component
    (group_key = "g:<smallest node name>"). Rows with neither become singletons ("r:<row_id>").
    Derived (D39) rows take project, commit and therefore component from their parent.
    """
    if not df.index.equals(pd.RangeIndex(len(df))):
        raise ValueError("df must have a default RangeIndex (row_id = position)")
    n = len(df)
    parent = np.full(n, -1, dtype=np.int64) if parent_row_id is None else np.asarray(parent_row_id)
    if len(parent) != n or np.any(parent >= n) or np.any(parent < -1):
        raise ValueError("parent_row_id must match df length and hold -1 or valid row positions")

    projects = [canonical_project(v) for v in df["project"]]
    commits = [normalize_commit(v) for v in df["commit"]]
    for rid in np.flatnonzero(parent >= 0):
        projects[rid], commits[rid] = projects[parent[rid]], commits[parent[rid]]

    uf = _UnionFind()
    anchors, kinds = [], []
    for rid, (p, c) in enumerate(zip(projects, commits, strict=True)):
        pn, cn = (f"p:{p}" if p else None), (f"c:{c}" if c else None)
        for node in (pn, cn):
            if node:
                uf.add(node)
        if pn and cn:
            uf.union(pn, cn)
        if cn:
            anchors.append(cn)
            kinds.append("commit")
        elif pn:
            anchors.append(pn)
            kinds.append("project_only")
        else:
            node = f"r:{rid}"
            uf.add(node)
            anchors.append(node)
            kinds.append("row")

    return pd.DataFrame(
        {
            "row_id": np.arange(n),
            "project_key": projects,
            "commit_key": commits,
            "group_key": ["g:" + uf.find(a) for a in anchors],
            "group_kind": kinds,
            "parent_row_id": parent,
        }
    )


# --------------------------------------------------------------------------- D39 (unchanged)
def add_patched_negatives(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, dict]:
    """D39 (opt-in): add `fixed_code` of Python vulnerable rows as label-0 rows.

    Only Python rows with a non-empty `fixed_code` that differs from `code` are used. New rows
    get source "<source>:patched", cwe [], fixed_code NA, and inherit the parent's group in
    `make_assignments` (so a function and its patched twin never straddle splits). Patched
    code already present in the data (whitespace-insensitive) is skipped.
    Returns (df with new rows appended, parent_row_id array with -1 for original rows, stats).
    """
    n = len(df)
    parent = np.full(n, -1, dtype=np.int64)
    py = df[(df["language"] == "python") & (df["label"] == 1)]
    fixed = py["fixed_code"].astype(object)
    cand = py[fixed.notna() & (fixed.str.strip() != "") & (fixed != py["code"])]

    squash = lambda s: s.astype(object).str.replace(r"\s+", "", regex=True)  # noqa: E731
    existing = set(squash(df["code"]))
    new_rows, parents, seen = [], [], set()
    for rid, row in cand.iterrows():
        key = squash(pd.Series([row["fixed_code"]])).iloc[0]
        if key in existing or key in seen:
            continue
        seen.add(key)
        new = row.copy()
        new["code"], new["label"], new["cwe"] = row["fixed_code"], 0, []
        new["fixed_code"] = pd.NA
        new["source"] = f"{row['source']}:patched"
        new_rows.append(new)
        parents.append(rid)

    stats = {
        "enabled": True,
        "python_positive_rows": len(py),
        "candidates_with_fixed_code": len(cand),
        "added": len(new_rows),
        "skipped_duplicates": len(cand) - len(new_rows),
    }
    if not new_rows:
        return df, parent, stats
    added = pd.DataFrame(new_rows)[schema.COLUMNS].astype(schema.DTYPES)
    added["cwe"] = [[] for _ in range(len(added))]
    out = pd.concat([df, added], ignore_index=True)
    return out, np.concatenate([parent, np.array(parents, dtype=np.int64)]), stats


def d39_applicability(df: pd.DataFrame) -> dict:
    """Disabled-policy report: how many Python rows per label and how many have fixed_code."""
    py = df[df["language"] == "python"]
    return {
        "enabled": False,
        "python_rows": len(py),
        "python_label_0": int((py["label"] == 0).sum()),
        "python_label_1": int((py["label"] == 1).sum()),
        "python_positive_with_fixed_code": int(
            (
                (py["label"] == 1) & py["fixed_code"].notna() & (py["fixed_code"].str.strip() != "")
            ).sum()
        ),
    }


# --------------------------------------------------------------------------- optimization
def _feature_matrix(df: pd.DataFrame, keys: pd.DataFrame):
    """Per-component feature counts: [rows, positives, one column per CWE (vulnerable rows)]."""
    gid, uniq = pd.factorize(keys["group_key"], sort=True)
    G = len(uniq)
    label = df["label"].to_numpy(dtype="int64")

    vuln = df.loc[label == 1, "cwe"].map(lambda c: _cwe_list(c) or ["NONE"])
    ex = vuln.explode()
    cw = pd.DataFrame({"g": gid[ex.index.to_numpy()], "cwe": ex.to_numpy()})
    table = cw.groupby(["g", "cwe"]).size().unstack(fill_value=0).reindex(range(G), fill_value=0)

    M = np.zeros((G, 2 + table.shape[1]))
    M[:, 0] = np.bincount(gid, minlength=G)
    M[:, 1] = np.bincount(gid[label == 1], minlength=G)
    M[:, 2:] = table.to_numpy()
    names = ["rows", "positives"] + [f"cwe:{c}" for c in table.columns]
    return M, names, uniq, gid


def optimize_assignment(
    M: np.ndarray,
    allowed: np.ndarray,
    ratios: dict[str, float] = RATIOS,
    seed: int = SEED,
    refine_top: int = REFINE_TOP,
    passes: int = REFINE_PASSES,
) -> tuple[np.ndarray, dict]:
    """Assign each component (row of M) to a split index, minimizing
    sum_f w_f * sum_s ((count_sf - target_sf) / total_f)^2.

    Dividing by total_f gives every CWE equal importance regardless of size, so rare CWEs are
    balanced as well as the group structure allows. Deterministic for a fixed seed.
    """
    G, F = M.shape
    S = len(SPLITS)
    tot = M.sum(axis=0)
    tot[tot == 0] = 1.0
    w = np.full(F, FEATURE_WEIGHTS["cwe"])
    w[0], w[1] = FEATURE_WEIGHTS["rows"], FEATURE_WEIGHTS["positives"]
    Mn = M / tot * np.sqrt(w)
    ratio_vec = np.array([ratios[s] for s in SPLITS])
    T = ratio_vec[:, None] * Mn.sum(axis=0)[None, :]

    rng = np.random.default_rng(seed)
    mass = Mn.sum(axis=1)
    order = np.lexsort((rng.permutation(G), -mass))  # heaviest first, seeded tie-break

    cur = np.zeros((S, F))
    assign = np.zeros(G, dtype=np.int64)
    for g in order:
        v = Mn[g]
        delta = (2 * (cur - T) + v) @ v
        delta = np.where(allowed[g], delta, np.inf)
        s = int(np.argmin(delta))
        assign[g] = s
        cur[s] += v

    moves = 0
    for _ in range(passes):
        moved = 0
        for g in order[:refine_top]:
            s0, v = assign[g], Mn[g]
            delta = (v - 2 * (cur[s0] - T[s0])) @ v + (2 * (cur - T) + v) @ v
            delta[~allowed[g]] = np.inf
            delta[s0] = np.inf
            s1 = int(np.argmin(delta))
            if delta[s1] < -1e-12:
                cur[s0] -= v
                cur[s1] += v
                assign[g] = s1
                moved += 1
        moves += moved
        if not moved:
            break

    return assign, {
        "method": SPLIT_METHOD,
        "components": int(G),
        "features": int(F),
        "final_loss": float(((cur - T) ** 2).sum()),
        "local_search_moves": int(moves),
        "refine_top": int(refine_top),
        "passes": int(passes),
    }


def make_assignments(
    df: pd.DataFrame,
    parent_row_id: np.ndarray | None = None,
    seed: int = SEED,
    ratios: dict[str, float] = RATIOS,
    return_info: bool = False,
):
    """Assign whole components to splits. Every project and commit lands in exactly one split."""
    keys = build_group_keys(df, parent_row_id)
    M, _, uniq, gid = _feature_matrix(df, keys)

    unknown = keys["project_key"].isna().to_numpy().astype(float)
    has_unknown = np.bincount(gid, weights=unknown, minlength=len(uniq)) > 0
    allowed = np.ones((len(uniq), len(SPLITS)), dtype=bool)
    allowed[has_unknown, HOLDOUT_IDX] = False  # unknown project: disjointness unprovable

    comp_split, info = optimize_assignment(M, allowed, ratios, seed)
    info["components_barred_from_holdout"] = int(has_unknown.sum())
    keys["split"] = np.array(SPLITS, dtype=object)[comp_split[gid]]

    out = keys[
        ["row_id", "group_key", "group_kind", "project_key", "commit_key", "parent_row_id", "split"]
    ]
    return (out, info) if return_info else out


# --------------------------------------------------------------------------- validation
def validate_assignments(assign: pd.DataFrame, n_rows: int) -> list[str]:
    """Missing / duplicate rows, bad or empty splits, group, commit and project leakage."""
    problems = []
    dup = int(assign["row_id"].duplicated().sum())
    if dup:
        problems.append(f"duplicate assignments: {dup} row_ids assigned more than once")
    missing = set(range(n_rows)) - set(assign["row_id"])
    if missing:
        problems.append(
            f"missing rows: {len(missing)} row_ids have no split (e.g. {sorted(missing)[:5]})"
        )
    extra = set(assign["row_id"]) - set(range(n_rows))
    if extra:
        problems.append(f"unknown row_ids assigned: {sorted(extra)[:5]}")
    bad = sorted(set(assign["split"]) - set(SPLITS))
    if bad:
        problems.append(f"invalid split names: {bad}")
    for s in SPLITS:
        if not (assign["split"] == s).any():
            problems.append(f"split '{s}' is empty")

    def _crossing(col: str) -> pd.Series:
        sub = assign.dropna(subset=[col])
        n = sub.groupby(col)["split"].nunique()
        return n[n > 1]

    for col, label in (
        ("group_key", "group leakage"),
        ("commit_key", "commit leakage"),
        ("project_key", "project overlap"),
    ):
        if col not in assign:
            continue
        leaked = _crossing(col)
        if len(leaked):
            problems.append(
                f"{label}: {len(leaked)} {col}s span several splits (e.g. {list(leaked.index[:3])})"
            )

    if assign.loc[assign["split"] == "holdout", "project_key"].isna().any():
        problems.append("holdout contains rows with unknown project")
    return problems


def validate_saved(paths: dict[str, Path], assign: pd.DataFrame) -> list[str]:
    """Row counts of the written files must match the assignments."""
    problems = []
    for s, path in paths.items():
        rows = pq.ParquetFile(path).metadata.num_rows
        expect = int((assign["split"] == s).sum())
        if rows != expect:
            problems.append(f"{path.name}: {rows} rows on disk, {expect} assigned")
    return problems


def validate_cwe_distribution(
    df: pd.DataFrame,
    assign: pd.DataFrame,
    ratios: dict[str, float] = RATIOS,
    tol: float = TOL_ABS,
) -> dict:
    """Per-CWE (vulnerable rows, multilabel) share per split vs target, with flagged imbalances.

    An imbalance is *unavoidable* when the group structure forces it: fewer groups than splits,
    or one group holds more of the CWE than a small split's share. Others are *residual*
    (optimizer or holdout-constraint leftovers). Never raises; callers decide.
    """
    v = df.loc[df["label"] == 1, ["cwe"]].copy()
    v["split"] = assign.loc[v.index, "split"].to_numpy()
    v["group"] = assign.loc[v.index, "group_key"].to_numpy()
    v["cwe"] = v["cwe"].map(lambda c: _cwe_list(c) or ["NONE"])
    if v.empty:
        return {
            "tolerance": tol,
            "targets": dict(ratios),
            "per_cwe": {},
            "unavoidable": [],
            "residual": [],
            "summary": {"cwes": 0, "balanced": 0, "unavoidable": 0, "residual": 0},
        }
    ex = v.explode("cwe")

    rows = (
        ex.groupby(["cwe", "split"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=list(SPLITS), fill_value=0)
    )
    groups = (
        ex.groupby(["cwe", "split"])["group"]
        .nunique()
        .unstack(fill_value=0)
        .reindex(columns=list(SPLITS), fill_value=0)
    )
    n_groups = ex.groupby("cwe")["group"].nunique()
    max_group = ex.groupby(["cwe", "group"]).size().groupby("cwe").max()
    small = min(ratios.values())

    per_cwe, unavoidable, residual = {}, [], []
    for cwe in rows.index:
        total = int(rows.loc[cwe].sum())
        shares = {s: round(float(rows.loc[cwe, s] / total), 4) for s in SPLITS}
        issues = [
            {
                "split": s,
                "share": shares[s],
                "target": ratios[s],
                "deviation": round(shares[s] - ratios[s], 4),
            }
            for s in SPLITS
            if abs(shares[s] - ratios[s]) > tol or (s != "train" and rows.loc[cwe, s] == 0)
        ]
        max_share = round(float(max_group[cwe] / total), 4)
        reasons = []
        if issues:
            if n_groups[cwe] < len(SPLITS):
                reasons.append(f"fewer groups ({int(n_groups[cwe])}) than splits ({len(SPLITS)})")
            if max_share > small + tol:
                reasons.append(f"dominant group holds {max_share:.0%} of the CWE")
        per_cwe[cwe] = {
            "rows": total,
            "groups": int(n_groups[cwe]),
            "largest_group_share": max_share,
            "rows_by_split": {s: int(rows.loc[cwe, s]) for s in SPLITS},
            "groups_by_split": {s: int(groups.loc[cwe, s]) for s in SPLITS},
            "share_by_split": shares,
            "issues": issues,
            "unavoidable_reasons": reasons,
            "missing_from": [s for s in SPLITS if rows.loc[cwe, s] == 0],
        }
        if issues:
            (unavoidable if reasons else residual).append(cwe)

    return {
        "tolerance": tol,
        "targets": dict(ratios),
        "per_cwe": dict(sorted(per_cwe.items())),
        "unavoidable": sorted(unavoidable),
        "residual": sorted(residual),
        "summary": {
            "cwes": len(per_cwe),
            "balanced": len(per_cwe) - len(unavoidable) - len(residual),
            "unavoidable": len(unavoidable),
            "residual": len(residual),
        },
    }


# --------------------------------------------------------------------------- manifest
def _split_summary(df: pd.DataFrame, assign: pd.DataFrame) -> dict:
    out = {}
    for s in SPLITS:
        m = (assign["split"] == s).to_numpy()
        part, a = df[m], assign[m]
        gsz = a.groupby("group_key").size()
        out[s] = {
            "rows": int(m.sum()),
            "ratio": round(float(m.mean()), 4),
            "label_1": int((part["label"] == 1).sum()),
            "label_0": int((part["label"] == 0).sum()),
            "groups": len(gsz),
            "projects": int(a["project_key"].nunique()),
            "unknown_project_rows": int(a["project_key"].isna().sum()),
            "largest_group_rows": int(gsz.max()) if len(gsz) else 0,
            "largest_group_share": round(float(gsz.max() / m.sum()), 4) if m.sum() else 0.0,
            "rows_by_source": {
                k: int(v) for k, v in part["source"].value_counts().sort_index().items()
            },
            "rows_by_language": {
                str(k): int(v) for k, v in part["language"].value_counts().sort_index().items()
            },
        }
    return out


def _ratio_deviation(summary: dict, ratios: dict[str, float] = RATIOS) -> dict:
    dev = {s: round(summary[s]["ratio"] - ratios[s], 4) for s in SPLITS}
    return {
        "deviation": dev,
        "tolerance": RATIO_TOL,
        "flagged": [s for s, d in dev.items() if abs(d) > RATIO_TOL],
    }


def _per_cwe(df: pd.DataFrame, assign: pd.DataFrame) -> dict:
    v = df.loc[df["label"] == 1, ["cwe"]].copy()
    v["split"], v["group_key"] = assign.loc[v.index, "split"], assign.loc[v.index, "group_key"]
    v["cwe"] = v["cwe"].map(lambda c: _cwe_list(c) or ["NONE"])
    if v.empty:
        return {}
    stats = (
        v.explode("cwe")
        .groupby(["cwe", "split"])
        .agg(rows=("group_key", "size"), groups=("group_key", "nunique"))
    )
    out: dict = {}
    for (cwe, split), r in stats.iterrows():
        out.setdefault(cwe, {})[split] = {"rows": int(r["rows"]), "groups": int(r["groups"])}
    return dict(sorted(out.items()))


def _diagnostics(df: pd.DataFrame, assign: pd.DataFrame) -> dict:
    e = df[["cve"]].assign(split=assign["split"].to_numpy()).explode("cve").dropna(subset=["cve"])
    cve_cross = int((e.groupby("cve")["split"].nunique() > 1).sum()) if len(e) else 0

    sizes = assign.groupby("group_key").size()
    projs = assign.dropna(subset=["project_key"]).groupby("group_key")["project_key"].nunique()
    merged = projs[projs > 1].sort_values(ascending=False)
    names = pd.Series(assign["project_key"].dropna().unique())
    base = names.str.split("/").str[-1]
    variants = int((base.map(base.value_counts()) > 1).sum()) if len(names) else 0
    return {
        "group_kinds": {
            k: int(v) for k, v in assign["group_kind"].value_counts().sort_index().items()
        },
        "raw_project_names": int(df["project"].dropna().nunique()),
        "canonical_project_names": int(assign["project_key"].nunique()),
        "components": len(sizes),
        "largest_component_rows": int(sizes.max()),
        "largest_component_share": round(float(sizes.max() / len(assign)), 4),
        "components_merging_multiple_projects": len(merged),
        "largest_merged_components": [
            {"group": g, "projects": int(n), "rows": int(sizes[g])}
            for g, n in merged.head(5).items()
        ],
        "cve_ids_crossing_splits": cve_cross,
        "project_name_variants_suspected": variants,
    }


def build_splits(
    interim_dir: Path = merge.INTERIM_DIR,
    splits_dir: Path = SPLITS_DIR,
    manifest_path: Path = MANIFEST_PATH,
    seed: int = SEED,
    d39_patched_negatives: bool = False,
    strict_cwe: bool = False,
) -> dict:
    """Merge, split, validate, write split files and the manifest. Returns the manifest dict.

    Writes only under `splits_dir` and `manifest_path`; input datasets are never modified.
    """
    if Path(splits_dir).resolve() == Path(interim_dir).resolve():
        raise SplitValidationError(
            "splits_dir must differ from interim_dir (inputs are never overwritten)"
        )

    merged_path = Path(interim_dir) / "merged_datasets.parquet"

    if not merged_path.exists():
        raise FileNotFoundError(
            f"Merged dataset not found: {merged_path}\n"
            "Run merge.py first to create merged_datasets.parquet."
        )

    print(f"Loading merged dataset: {merged_path}")

    df = schema.from_parquet(merged_path)
    problems = schema.validate(df)
    if problems:
        raise SplitValidationError(f"merged dataset breaks the schema: {'; '.join(problems[:5])}")

    n_merged = len(df)
    inputs = [
        {
            "file": merged_path.name,
            "sha256": hashlib.sha256(merged_path.read_bytes()).hexdigest(),
            "rows": n_merged,
        }
    ]

    aliases_path = DOCS_PROJECT_NAMES_DIR / "project_aliases.json"
    if aliases_path.exists():
        inputs.append(
            {
                "file": aliases_path.name,
                "sha256": hashlib.sha256(aliases_path.read_bytes()).hexdigest(),
                "rows": len(json.loads(aliases_path.read_text(encoding="utf-8"))["aliases"]),
            }
        )
    else:
        print(
            "  WARNING: docs/datasets/project_names/project_aliases.json not found; "
            "run project_normalization first"
        )

    cross_dups = merge.count_cross_source_duplicates(df)

    print(f"Loaded {n_merged:,} rows from merged dataset.")

    parent = None
    if d39_patched_negatives:
        df, parent, d39 = add_patched_negatives(df)
    else:
        d39 = d39_applicability(df)
    assign, opt_info = make_assignments(df, parent, seed, return_info=True)

    problems = validate_assignments(assign, len(df))
    if problems:
        raise SplitValidationError("; ".join(problems))

    cwe_report = validate_cwe_distribution(df, assign)
    if strict_cwe and cwe_report["residual"]:
        raise SplitValidationError(f"avoidable CWE imbalance remains: {cwe_report['residual']}")

    splits_dir, manifest_path = Path(splits_dir), Path(manifest_path)
    splits_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    paths = {}
    for s in SPLITS:
        paths[s] = splits_dir / f"{s}.parquet"
        schema.to_parquet(df[(assign["split"] == s).to_numpy()].reset_index(drop=True), paths[s])
    assign_path = splits_dir / "assignments.parquet"
    assign.to_parquet(assign_path, index=False)
    problems = validate_saved(paths, assign)
    if problems:
        raise SplitValidationError("; ".join(problems))

    dataset_hash = hashlib.sha256(
        "\n".join(
            f"{i['file']}:{i['sha256']}" for i in sorted(inputs, key=lambda i: i["file"])
        ).encode()
    ).hexdigest()
    hold = assign[assign["split"] == "holdout"]
    summary = _split_summary(df, assign)
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "task": "W2-P1-01",
        "seed": seed,
        "schema_version": schema.SCHEMA_VERSION,
        "dataset_hash": dataset_hash,
        "inputs": inputs,
        "rows_merged": n_merged,
        "rows_total": len(df),
        "cross_source_duplicate_codes": cross_dups,
        "split_method": SPLIT_METHOD,
        "project_normalizer": NORMALIZER_NAME,
        "optimizer": opt_info,
        "target_ratios": RATIOS,
        "splits": summary,
        "ratio_deviation": _ratio_deviation(summary),
        "holdout_projects": sorted(hold["project_key"].dropna().unique().tolist()),
        "d39_negatives": d39,
        "diagnostics": _diagnostics(df, assign),
        "per_cwe": _per_cwe(df, assign),
        "cwe_balance": cwe_report,
        "validation": {
            "passed": True,
            "checks": [
                "missing rows",
                "duplicate assignments",
                "group leakage",
                "commit leakage",
                "project overlap (all splits)",
                "holdout unknown project",
                "saved row counts",
                "cwe distribution (reported, not fatal unless --strict-cwe)",
            ],
        },
        "files": {s: str(p) for s, p in paths.items()} | {"assignments": str(assign_path)},
        "group_key_rules": {
            "group": (
                "g:<smallest node> of a connected component over canonical projects and commits"
            ),
            "project_node": "p:<canonical project>",
            "commit_node": "c:<commit>",
            "row": "r:<row_id> (singleton when neither project nor commit is known)",
        },
        "limitations": LIMITATIONS,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(paths)} split files to {splits_dir} and manifest to {manifest_path}")
    for s, info in summary.items():
        print(f"  {s:8s} rows={info['rows']:>9,} ({info['ratio']:.1%})  groups={info['groups']:,}")
    if manifest["ratio_deviation"]["flagged"]:
        print(
            f"  WARNING ratio deviation > {RATIO_TOL:.0%}: {manifest['ratio_deviation']['flagged']}"
        )
    print(f"  CWE balance: {cwe_report['summary']}")
    if cwe_report["unavoidable"]:
        print(f"  Unavoidable CWE imbalance (rare / dominant group): {cwe_report['unavoidable']}")
    if cwe_report["residual"]:
        print(f"  Residual CWE imbalance: {cwe_report['residual']}")
    return manifest


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--interim-dir", type=Path, default=merge.INTERIM_DIR)
    p.add_argument("--splits-dir", type=Path, default=SPLITS_DIR)
    p.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument(
        "--d39-patched-negatives",
        action="store_true",
        help="add patched Python code as label-0 rows (D39; off until agreed)",
    )
    p.add_argument(
        "--strict-cwe",
        action="store_true",
        help="fail if an avoidable (residual) CWE imbalance remains",
    )
    a = p.parse_args(argv)
    build_splits(
        a.interim_dir, a.splits_dir, a.manifest, a.seed, a.d39_patched_negatives, a.strict_cwe
    )


if __name__ == "__main__":
    main()
