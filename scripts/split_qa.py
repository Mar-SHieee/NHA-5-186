"""Split QA: leakage checks and per-split / per-CWE statistics for a split manifest.

Run from the repository root:
    python scripts/split_qa.py [--manifest docs/dataset_manifest_v0.json]

Writes docs/split_qa.md (+ docs/split_qa_cwe.csv). Exit code 1 when a (project, commit) group,
commit, project, CVE component or exact code hash crosses a split, or the manifest row counts
do not match the files on disk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

try:
    from shield_core.datasets.project_normalization import normalize_project_name
except Exception:  # noqa: BLE001 - fall back to plain cleanup when the package is unavailable

    def normalize_project_name(value):  # type: ignore[misc]
        if value is None or pd.isna(value):
            return pd.NA
        return str(value).strip().lower() or pd.NA


MANIFEST_PATH = REPO_ROOT / "docs" / "dataset_manifest_v0.json"
REPORT_PATH = REPO_ROOT / "docs" / "split_qa.md"
SPLITS_DIR = REPO_ROOT / "data" / "interim" / "splits"
MAPPING_DIR = REPO_ROOT / "data" / "interim"
COLUMNS = ["code", "label", "cwe", "project", "commit", "cve", "source"]
EXAMPLES = 10

_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)


def _normalize_cve(cve: str) -> str | None:
    """Normalize CVE ID: strip, uppercase, validate pattern."""
    if cve is None or pd.isna(cve):
        return None
    text = str(cve).strip().upper()
    if not text:
        return None
    # Extract valid CVE pattern
    m = _CVE_RE.search(text)
    if not m:
        # If already looks like CVE-xxx but with spaces, try cleaned
        cleaned = re.sub(r"\s+", "", text)
        m2 = _CVE_RE.search(cleaned)
        return m2.group(0).upper() if m2 else None
    return m.group(0).upper()


@dataclass
class Check:
    name: str
    description: str
    count: int
    fatal: bool = True
    examples: pd.DataFrame | None = None

    @property
    def status(self) -> str:
        if self.count == 0:
            return "PASS"
        return "FAIL" if self.fatal else "WARN"


@dataclass
class QAResult:
    manifest: dict
    checks: list[Check] = field(default_factory=list)
    split_table: pd.DataFrame = field(default_factory=pd.DataFrame)
    cwe_table: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status == "FAIL"]


def _as_list(value) -> list:
    return list(value) if isinstance(value, (list, tuple, np.ndarray)) else []


def _clean_key(value) -> str | None:
    if value is None or value is pd.NA or (isinstance(value, float) and np.isnan(value)):
        return None
    text = str(value).strip().lower()
    return None if text in {"", "nan", "none", "null", "na", "<na>"} else text


def _canonical(values: pd.Series) -> pd.Series:
    cache = {}
    for v in values.dropna().unique():
        out = normalize_project_name(v)
        cache[v] = None if out is None or pd.isna(out) else _clean_key(out)
    return values.map(cache)


def load_splits(manifest: dict, splits_dir: Path) -> pd.DataFrame:
    frames = []
    for split in manifest["splits"]:
        path = Path(splits_dir) / f"{split}.parquet"
        if not path.exists() and split in manifest.get("files", {}):
            path = Path(splits_dir) / Path(manifest["files"][split]).name
        if not path.exists():
            raise FileNotFoundError(f"split file not found: {path}")
        part = pd.read_parquet(path)
        keep = [c for c in COLUMNS if c in part.columns]
        frames.append(part[keep].assign(split=split))
    df = pd.concat(frames, ignore_index=True)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None
    df["cwe"] = df["cwe"].map(_as_list)
    df["cve"] = df["cve"].map(_as_list)
    # Normalize CVE IDs to uppercase stripped BEFORE any union
    df["cve"] = df["cve"].map(lambda lst: [c for c in (_normalize_cve(x) for x in lst) if c])
    df["project_key"] = _canonical(df["project"])
    df["commit_key"] = df["commit"].map(_clean_key)
    both = df["project_key"].notna() & df["commit_key"].notna()
    df["group"] = (df["project_key"] + "|" + df["commit_key"]).where(both)
    return df


def _crossing(df: pd.DataFrame, key: str) -> pd.DataFrame:
    sub = df.dropna(subset=[key])
    n = sub.groupby(key)["split"].nunique()
    bad = sub[sub[key].isin(n[n > 1].index)]
    if bad.empty:
        return pd.DataFrame(columns=[key, "splits", "rows"])
    out = bad.groupby(key)["split"].agg(splits=lambda s: ", ".join(sorted(set(s))), rows="size")
    return out.sort_values("rows", ascending=False).reset_index()


def _load_mapping_edges(mapping_dir: Path | None) -> pd.DataFrame:
    if not mapping_dir or not Path(mapping_dir).exists():
        return pd.DataFrame(columns=["commit", "cve"])
    frames = []
    for path in sorted(Path(mapping_dir).glob("*_commit_cve_mapping.parquet")):
        part = pd.read_parquet(path)
        if {"commit", "cve"} <= set(part.columns):
            frames.append(part[["commit", "cve"]])
    if not frames:
        return pd.DataFrame(columns=["commit", "cve"])
    df = pd.concat(frames, ignore_index=True).dropna().drop_duplicates()
    # Normalize CVE IDs in mapping too
    df["cve"] = df["cve"].map(_normalize_cve)
    df["commit"] = df["commit"].map(_clean_key)
    return df.dropna().drop_duplicates()


def cve_components(df: pd.DataFrame, mapping: pd.DataFrame) -> pd.Series:
    """Component id per row. CVEs are linked when they share a row or a commit.

    FIX: All CVE IDs are normalized to uppercase stripped before union-find.
    """
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    # CVEs in same row are linked (already normalized)
    for cves in {tuple(sorted(c)) for c in df["cve"] if len(c) > 1}:
        for other in cves[1:]:
            union(cves[0], other)

    # CVEs sharing a commit are linked
    with_cve = df.loc[df["cve"].map(len) > 0, ["commit_key", "cve"]].explode("cve")
    pairs = with_cve.dropna().drop_duplicates()
    for commit, cve in zip(pairs["commit_key"], pairs["cve"], strict=True):
        if commit and cve:
            union(f"c:{commit}", cve)

    # Mapping file edges - already normalized
    for commit, cve in zip(mapping["commit"], mapping["cve"], strict=True):
        if commit and cve:
            union(f"c:{commit}", cve)

    comps = []
    for commit, cves in zip(df["commit_key"], df["cve"], strict=True):
        if cves:
            comps.append(find(cves[0]))
        elif commit and f"c:{commit}" in parent:
            comps.append(find(f"c:{commit}"))
        else:
            comps.append(None)
    return pd.Series(comps, index=df.index, dtype=object)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def hash_overlap(df: pd.DataFrame, squash: bool = False) -> pd.DataFrame:
    def _norm(code):
        if code is None or pd.isna(code):
            return None
        s = str(code)
        if squash:
            s = re.sub(r"\s+", "", s)
        return s

    tmp = df[["code", "split"]].copy()
    tmp["h"] = tmp["code"].map(_norm).map(lambda x: _hash(x) if x else None)
    tmp = tmp.dropna(subset=["h"])
    n = tmp.groupby("h")["split"].nunique()
    bad = tmp[tmp["h"].isin(n[n > 1].index)]
    if bad.empty:
        return pd.DataFrame(columns=["hash", "splits", "rows"])
    out = bad.groupby("h")["split"].agg(splits=lambda s: ", ".join(sorted(set(s))), rows="size")
    return out.sort_values("rows", ascending=False).reset_index().rename(columns={"h": "hash"})


def split_table(df: pd.DataFrame, manifest: dict) -> pd.DataFrame:
    rows = []
    for split in manifest["splits"]:
        part = df[df["split"] == split]
        if part.empty:
            continue
        rows.append(
            {
                "split": split,
                "rows": len(part),
                "share": round(len(part) / len(df), 4) if len(df) else 0,
                "target": manifest["target_ratios"].get(split),
                "label_1": int((part["label"] == 1).sum()),
                "label_0": int((part["label"] == 0).sum()),
                "projects": int(part["project_key"].nunique()),
                "commit_groups": int(
                    part["group"].nunique() + part["commit_key"].nunique() - part["group"].nunique()
                ),
                "cves": int(part.explode("cve")["cve"].nunique()),
                "largest_group_share": round(
                    part["group"].value_counts(normalize=True).max()
                    if part["group"].notna().any()
                    else 0,
                    4,
                ),
                "largest_project_share": round(
                    part["project_key"].value_counts(normalize=True).max()
                    if part["project_key"].notna().any()
                    else 0,
                    4,
                ),
            }
        )
    return pd.DataFrame(rows)


def cwe_table(df: pd.DataFrame, splits: list[str]) -> pd.DataFrame:
    ex = df.explode("cwe")
    ex = ex[ex["cwe"].notna() & (ex["cwe"] != "")]
    if ex.empty:
        return pd.DataFrame(columns=["cwe", "rows"])
    out = ex.groupby("cwe").size().to_frame("rows")
    for s in splits:
        out[f"rows_{s}"] = ex[ex["split"] == s].groupby("cwe").size()
    out["projects"] = ex.groupby("cwe")["project_key"].nunique()
    out["commit_groups"] = ex.groupby("cwe")["group"].nunique()
    out["cves"] = ex.explode("cve").dropna(subset=["cve"]).groupby("cwe")["cve"].nunique()
    out["cves"] = out["cves"].fillna(0).astype(int)
    biggest_group = ex.dropna(subset=["group"]).groupby(["cwe", "group"]).size()
    out["largest_group_share"] = (biggest_group.groupby("cwe").max() / out["rows"]).round(4)
    biggest_project = ex.dropna(subset=["project_key"]).groupby(["cwe", "project_key"]).size()
    out["largest_project_share"] = (biggest_project.groupby("cwe").max() / out["rows"]).round(4)
    out = out.fillna(0)
    return out.sort_values("rows", ascending=False).rename_axis("cwe").reset_index()


def run_qa(
    manifest_path: Path = MANIFEST_PATH,
    splits_dir: Path = SPLITS_DIR,
    mapping_dir: Path | None = MAPPING_DIR,
) -> QAResult:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    df = load_splits(manifest, splits_dir)
    result = QAResult(manifest=manifest)

    on_disk = df["split"].value_counts().to_dict()
    declared = {s: v["rows"] for s, v in manifest["splits"].items()}
    mismatch = pd.DataFrame(
        [
            {"split": s, "manifest_rows": declared[s], "file_rows": int(on_disk.get(s, 0))}
            for s in declared
            if declared[s] != on_disk.get(s, 0)
        ]
    )
    result.checks.append(
        Check(
            "manifest row counts",
            "rows per split equal the manifest",
            len(mismatch),
            examples=mismatch,
        )
    )

    for key, name, desc in (
        ("group", "(project, commit) group crossing", "one (project, commit) group in >1 split"),
        ("commit_key", "commit crossing", "one commit hash in >1 split"),
        ("project_key", "project crossing", "one project in >1 split"),
    ):
        bad = _crossing(df, key)
        result.checks.append(Check(name, desc, len(bad), examples=bad.head(EXAMPLES)))

    mapping = _load_mapping_edges(mapping_dir)
    df["cve_component"] = cve_components(df, mapping)
    comp = _crossing(df, "cve_component")
    if len(comp):
        members = (
            df.dropna(subset=["cve_component"])
            .explode("cve")
            .groupby("cve_component")
            .agg(
                cves=("cve", lambda s: ", ".join(sorted({str(x) for x in s.dropna()})[:4])),
                projects=("project_key", lambda s: ", ".join(sorted(set(s.dropna()))[:4])),
            )
        )
        comp = comp.merge(members, left_on="cve_component", right_index=True, how="left")
    result.checks.append(
        Check(
            "CVE component crossing",
            "CVEs linked by a shared row or commit appear in >1 split",
            len(comp),
            examples=comp.head(EXAMPLES),
        )
    )

    exact = hash_overlap(df, squash=False)
    result.checks.append(
        Check(
            "exact code-hash overlap",
            "identical code in >1 split",
            len(exact),
            examples=exact.head(EXAMPLES),
        )
    )
    squashed = hash_overlap(df, squash=True)
    result.checks.append(
        Check(
            "whitespace-insensitive overlap",
            "same code ignoring whitespace in >1 split",
            len(squashed),
            fatal=False,
            examples=squashed.head(EXAMPLES),
        )
    )

    cve_rows = df[["split", "cve"]].explode("cve").dropna()
    n_cve = cve_rows.groupby("cve")["split"].nunique()
    result.checks.append(
        Check(
            "CVE ids in >1 split",
            "single CVE id seen in more than one split (information)",
            int((n_cve > 1).sum()),
            fatal=False,
        )
    )

    result.split_table = split_table(df, manifest)
    result.cwe_table = cwe_table(df, list(manifest["splits"]))
    return result


def _md(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "_none_\n"
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + " --- |" * len(cols)]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(lines) + "\n"


def write_report(result: QAResult, path: Path, cwe_csv: Path | None, top_cwe: int) -> None:
    m = result.manifest
    verdict = "FAIL" if result.failures else "PASS"
    lines = [
        "# Split QA",
        "",
        f"**Verdict: {verdict}**"
        + (f" ({', '.join(c.name for c in result.failures)})" if result.failures else ""),
        "",
        f"Manifest {m.get('manifest_version', '?')} · seed {m.get('seed', '?')} · "
        f"dataset_hash `{str(m.get('dataset_hash', ''))[:12]}`",
        "",
        "## Checks",
        "",
        _md(
            pd.DataFrame(
                [
                    {
                        "check": c.name,
                        "violations": c.count,
                        "status": c.status,
                        "meaning": c.description,
                    }
                    for c in result.checks
                ]
            )
        ),
        "## Per split",
        "",
        _md(result.split_table),
        f"## Per CWE (vulnerable rows, top {top_cwe} of {len(result.cwe_table)})",
        "",
        _md(result.cwe_table.head(top_cwe)),
    ]
    for c in result.checks:
        if c.count and c.examples is not None and not c.examples.empty:
            lines += [f"## Examples: {c.name}", "", _md(c.examples)]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    if cwe_csv is not None:
        result.cwe_table.to_csv(cwe_csv, index=False)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    p.add_argument("--splits-dir", type=Path, default=SPLITS_DIR)
    p.add_argument("--mapping-dir", type=Path, default=MAPPING_DIR)
    p.add_argument("--report", type=Path, default=REPORT_PATH)
    p.add_argument("--top-cwe", type=int, default=40)
    a = p.parse_args(argv)

    result = run_qa(a.manifest, a.splits_dir, a.mapping_dir)
    write_report(result, a.report, a.report.with_name(a.report.stem + "_cwe.csv"), a.top_cwe)
    for c in result.checks:
        print(f"  [{c.status}] {c.name}: {c.count}")
    print(f"Report: {a.report}")
    return 1 if result.failures else 0


if __name__ == "__main__":
    sys.exit(main())
