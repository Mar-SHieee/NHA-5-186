"""Build the code-metric table for V2 (W2-P5-02): six tree-sitter numbers per function.

Reads the split files V1 trains on and measures every distinct function once: the `code` of
every row, plus the `fixed_code` of vulnerable rows (V1 turns those into label-0 rows). Writes

  data/interim/code_metrics/code_metrics.parquet    one row per distinct (language, code)
  data/interim/code_metrics/code_metrics.meta.json  what the table was built from
  docs/modeling/code_metrics_report.md              numbers about the real data

The table is keyed by the TEXT of the code, not by row position. V1 adds rows (fixed code) and
drops rows (empty or duplicate code) after reading a split, so row order does not survive.

    python scripts/training/build_code_metrics.py              # all rows, about 10+ minutes
    python scripts/training/build_code_metrics.py --limit 2000 # quick trial, marked partial

In V2 training:

    from scripts.training.build_code_metrics import attach_code_metrics, load_code_metrics
    df = attach_code_metrics(df, load_code_metrics())
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shield_core import paths  # noqa: E402
from shield_core.extraction import ts_utils  # noqa: E402
from shield_core.extraction.ts_utils import FEATURE_NAMES, build_feature_table  # noqa: E402
from shield_core.languages import registry  # noqa: E402
from shield_core.tracking import hash_file  # noqa: E402

SPLIT_NAMES = ("train", "val", "test", "holdout")
KEY = ["language", "code_sha256"]
METRICS = [name for name in FEATURE_NAMES if name != "has_parse_error"]
TABLE_NAME = "code_metrics.parquet"
META_NAME = "code_metrics.meta.json"
DEFAULT_MANIFEST = paths.DOCS_AUDITS_DIR / "dataset_manifest_v0.json"
DEFAULT_REPORT = paths.DOCS_MODELING_DIR / "code_metrics_report.md"
_WANTED_COLUMNS = ("code", "fixed_code", "language", "label", "source")


class StaleCodeMetricsError(RuntimeError):
    """The table was built from other data or other metric code than the ones in use now."""


# ----------------------------------------------------------------------------- keys


def code_sha256(code: str) -> str:
    """Hash of a function's text. `ignore` drops characters that are not valid UTF-8."""
    return hashlib.sha256(code.encode("utf-8", "ignore")).hexdigest()


def _clean(code: str) -> str:
    """The same text without characters that cannot be encoded (a lone surrogate would crash)."""
    return code.encode("utf-8", "ignore").decode("utf-8")


# ----------------------------------------------------------------------------- reading


def _occurrences(
    frame: pd.DataFrame, split: str, enabled: list[str]
) -> tuple[pd.DataFrame, Counter]:
    """Every function text a model can see in one split, with its label, source and kind."""
    parts = [frame[["code", "language", "source", "label"]].assign(kind="code")]
    if "fixed_code" in frame:
        vulnerable = frame[(frame["label"] == 1) & frame["fixed_code"].notna()]
        changed = vulnerable["fixed_code"].astype(str) != vulnerable["code"].astype(str)
        fixed = vulnerable.loc[changed, ["fixed_code", "language", "source"]]
        fixed = fixed.rename(columns={"fixed_code": "code"})
        parts.append(fixed.assign(label=0, kind="fixed"))
    occ = pd.concat(parts, ignore_index=True)
    occ["code"] = occ["code"].astype("object")
    occ["split"] = split

    skipped: Counter = Counter()
    blank = occ["code"].fillna("").astype(str).str.strip().eq("").to_numpy()
    unsupported = ~occ["language"].isin(enabled).to_numpy()
    skipped["empty_code"] += int(blank.sum())
    for value, count in (
        occ.loc[unsupported & ~blank, "language"].value_counts(dropna=False).items()
    ):
        skipped[f"language:{value}"] += int(count)
    occ = occ.loc[~blank & ~unsupported].reset_index(drop=True)
    occ["code_sha256"] = [code_sha256(code) for code in occ["code"]]
    return occ, skipped


# ----------------------------------------------------------------------------- building


def _fingerprint_files() -> dict[str, str]:
    """Hashes of the code that defines the numbers. Line endings are ignored, so a Windows
    checkout and a Linux one agree."""
    files = [Path(ts_utils.__file__), *sorted(registry.LANGUAGES_DIR.glob("*.yaml"))]
    return {
        file.name: hashlib.sha256(file.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for file in files
    }


def _split_rows(splits_dir: Path) -> dict[str, int]:
    return {
        name: pq.ParquetFile(splits_dir / f"{name}.parquet").metadata.num_rows
        for name in SPLIT_NAMES
    }


def _read_manifest(manifest_path: Path) -> dict:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Split manifest is missing: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def build(
    splits_dir: Path,
    manifest_path: Path,
    out_dir: Path,
    report_path: Path | None,
    *,
    batch_size: int = 20_000,
    limit: int | None = None,
    log=print,
) -> dict:
    """Measure every distinct function of the splits and write the table, meta and report."""
    manifest = _read_manifest(manifest_path)
    for name in SPLIT_NAMES:
        if not (splits_dir / f"{name}.parquet").is_file():
            raise FileNotFoundError(f"Split file is missing: {splits_dir / f'{name}.parquet'}")
    enabled = registry.enabled_languages()
    started = time.perf_counter()

    seen: set[tuple[str, str]] = set()
    tables: list[pd.DataFrame] = []
    occurrences: list[pd.DataFrame] = []
    skipped: Counter = Counter()
    rows_read = measured = 0

    for split in SPLIT_NAMES:
        available = set(pq.ParquetFile(splits_dir / f"{split}.parquet").schema.names)
        frame = pd.read_parquet(
            splits_dir / f"{split}.parquet", columns=[c for c in _WANTED_COLUMNS if c in available]
        )
        rows_read += len(frame)
        occ, skip = _occurrences(frame, split, enabled)
        skipped.update(skip)
        del frame
        occurrences.append(occ.drop(columns="code"))

        pairs = list(zip(occ["language"], occ["code_sha256"], strict=True))
        new = ~occ.duplicated(KEY).to_numpy() & np.fromiter(
            (pair not in seen for pair in pairs), dtype=bool, count=len(pairs)
        )
        todo = occ.loc[new, [*KEY, "code"]]
        if limit is not None:
            todo = todo.iloc[: max(limit - measured, 0)]
        seen.update(zip(todo["language"], todo["code_sha256"], strict=True))
        log(f"[{split}] {len(occ):,} rows, {len(todo):,} new distinct functions to measure")

        split_start = time.perf_counter()
        for start in range(0, len(todo), batch_size):
            chunk = todo.iloc[start : start + batch_size]
            features = build_feature_table(
                pd.DataFrame(
                    {
                        "code": [_clean(code) for code in chunk["code"]],
                        "language": chunk["language"].to_numpy(),
                    }
                )
            )
            tables.append(chunk[KEY].reset_index(drop=True).join(features))
            done = min(start + batch_size, len(todo))
            speed = done / max(time.perf_counter() - split_start, 1e-9)
            eta = (len(todo) - done) / speed / 60
            log(f"  {done:,}/{len(todo):,}  {speed:,.0f} functions/s  about {eta:.1f} min left")
        measured += len(todo)
        del occ, todo

    table = pd.concat(tables, ignore_index=True) if tables else _empty_table()
    out_dir.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out_dir / TABLE_NAME, index=False)

    meta = {
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "manifest_version": manifest.get("manifest_version"),
        "manifest_dataset_hash": manifest.get("dataset_hash"),
        "split_rows": _split_rows(splits_dir),
        "split_file_hashes": {n: hash_file(splits_dir / f"{n}.parquet") for n in SPLIT_NAMES},
        "code_hashes": _fingerprint_files(),
        "feature_names": list(FEATURE_NAMES),
        "rows_read": rows_read,
        "distinct_functions": len(table),
        "skipped": dict(skipped),
        "limit": limit,
        "seconds": round(time.perf_counter() - started, 1),
    }
    (out_dir / META_NAME).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if report_path is not None and len(table):
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(_report(pd.concat(occurrences), table, meta), encoding="utf-8")
    log(f"Wrote {len(table):,} distinct functions to {out_dir / TABLE_NAME}")
    if skipped:
        log(f"WARNING: skipped rows: {dict(skipped)}")
    if limit is not None:
        log("PARTIAL RUN (--limit): load_code_metrics() will refuse this table.")
    return meta


def _empty_table() -> pd.DataFrame:
    table = pd.DataFrame({"language": [], "code_sha256": []}, dtype="object")
    for name in FEATURE_NAMES:
        table[name] = pd.Series(dtype="bool" if name == "has_parse_error" else "int32")
    return table


# ----------------------------------------------------------------------------- using it


def load_code_metrics(
    out_dir: Path | None = None,
    manifest_path: Path | None = None,
    splits_dir: Path | None = None,
    *,
    check: bool = True,
) -> pd.DataFrame:
    """Read the table. With `check`, refuse one built from other data or other metric code."""
    out_dir = out_dir or paths.CODE_METRICS_DIR
    meta_path = out_dir / META_NAME
    if not (out_dir / TABLE_NAME).is_file() or not meta_path.is_file():
        raise FileNotFoundError(f"No code-metric table in {out_dir}. Run build_code_metrics.py.")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if check:
        if meta.get("limit") is not None:
            raise StaleCodeMetricsError("this table is a partial run (--limit); rebuild it")
        manifest = _read_manifest(manifest_path or DEFAULT_MANIFEST)
        problems = []
        if manifest.get("dataset_hash") != meta["manifest_dataset_hash"]:
            problems.append("the dataset manifest hash changed")
        if _split_rows(splits_dir or paths.SPLITS_DIR) != meta["split_rows"]:
            problems.append("the number of rows in a split file changed")
        if _fingerprint_files() != meta["code_hashes"]:
            problems.append("ts_utils.py or a language yaml changed")
        if problems:
            raise StaleCodeMetricsError(
                "; ".join(problems) + ". Rebuild with build_code_metrics.py"
            )
    return pd.read_parquet(out_dir / TABLE_NAME)


def attach_code_metrics(
    df: pd.DataFrame,
    table: pd.DataFrame,
    code_col: str = "code",
    language_col: str = "language",
) -> pd.DataFrame:
    """Add the metric columns to `df`, matching rows by the text of the code.

    The index and the order of `df` are kept. A row whose code is not in the table is an error,
    not a missing value: it means the table was built from other data.
    """
    keys = df[code_col].map(lambda code: code_sha256(str(code)))
    right = table.rename(columns={"language": language_col})
    left = df.assign(code_sha256=keys.to_numpy())
    merged = left.merge(right, on=[language_col, "code_sha256"], how="left", validate="m:1")
    missing = merged[FEATURE_NAMES[0]].isna()
    if missing.any():
        first = df.index[missing.to_numpy()][:3].tolist()
        raise ValueError(
            f"{int(missing.sum())} rows have code that is not in the metric table "
            f"(first labels: {first}). Rebuild the table from the data you train on."
        )
    merged.index = df.index
    return merged.drop(columns="code_sha256").astype({n: table[n].dtype for n in FEATURE_NAMES})


# ----------------------------------------------------------------------------- report


def _cell(value) -> str:
    if isinstance(value, (float, np.floating)):
        return "-" if np.isnan(value) else f"{value:,.2f}"
    if isinstance(value, (int, np.integer)):
        return f"{value:,}"
    return str(value)


def _md(frame: pd.DataFrame) -> str:
    lines = [
        "| " + " | ".join(map(str, frame.columns)) + " |",
        "|" + "|".join("---" for _ in frame.columns) + "|",
    ]
    lines += [
        "| " + " | ".join(_cell(v) for v in row) + " |" for row in frame.itertuples(index=False)
    ]
    return "\n".join(lines)


def _spearman(a: pd.Series, b: pd.Series) -> float:
    """Rank correlation (Pearson on the ranks). NaN when one of the two never changes."""
    if a.nunique() < 2 or b.nunique() < 2:
        return float("nan")
    return float(a.rank().corr(b.rank()))


def _auc(values: pd.Series, labels: pd.Series) -> float:
    """Chance that a vulnerable function scores higher than a clean one (0.5 = no signal)."""
    positives = int(labels.sum())
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return float("nan")
    ranks = values.rank(method="average")
    return float(
        (ranks[labels == 1].sum() - positives * (positives + 1) / 2) / (positives * negatives)
    )


def _report(occurrences: pd.DataFrame, table: pd.DataFrame, meta: dict) -> str:
    rows = occurrences.merge(table, on=KEY, how="inner")
    originals = rows[rows["kind"] == "code"]
    fixed = int((rows["kind"] == "fixed").sum())
    languages = sorted(originals["language"].unique())

    by_source = (
        originals.groupby(["language", "source"])
        .agg(rows=("n_lines", "size"), parse_error_pct=("has_parse_error", "mean"))
        .reset_index()
    )
    by_source["parse_error_pct"] *= 100
    by_split = (
        originals.groupby(["split", "language"])
        .agg(rows=("n_lines", "size"), parse_error_pct=("has_parse_error", "mean"))
        .reset_index()
    )
    by_split["parse_error_pct"] *= 100

    spread = []
    for language in languages:
        part = originals[originals["language"] == language]
        for metric in METRICS:
            column = part[metric]
            spread.append(
                [language, metric, column.median(), column.quantile(0.95), int(column.max())]
            )
    spread = pd.DataFrame(spread, columns=["language", "metric", "median", "p95", "max"])

    others = [metric for metric in METRICS if metric != "n_lines"]
    correlation = pd.DataFrame({"metric": others})
    signal = pd.DataFrame({"metric": METRICS})
    for language in languages:
        part = originals[originals["language"] == language]
        correlation[language] = [_spearman(part[m], part["n_lines"]) for m in others]
        signal[language] = [_auc(part[m], part["label"]) for m in METRICS]

    skipped = meta["skipped"] or "none"
    partial = "" if meta["limit"] is None else f"\n**PARTIAL RUN: --limit {meta['limit']}**\n"
    return f"""# Code metrics report

Generated by `scripts/training/build_code_metrics.py` on {meta["created"]}. Do not edit by hand:
run the script again. Definitions are in `code_metrics.md`.
{partial}
## 1. Inputs

- Manifest: `{meta["manifest_version"]}`, dataset hash `{meta["manifest_dataset_hash"]}`
- Rows read from the split files: {meta["rows_read"]:,}
- Distinct functions measured: {meta["distinct_functions"]:,}
- Extra label-0 rows made from `fixed_code`: {fixed:,}
- Skipped rows: {skipped}
- Time: {meta["seconds"]:,} s

## 2. Rows and parse errors per language and source

`parse_error_pct` is the share of functions that tree-sitter could not read cleanly. The other
numbers of those rows are not reliable.

{_md(by_source)}

### Per split

{_md(by_split)}

## 3. How big the numbers are

{_md(spread)}

## 4. Do the numbers only repeat the length?

Spearman correlation of each metric with `n_lines` (1.0 means the same ordering as length).
A metric close to 1.0 adds little to a model that already has the length (plan, risk 5).

{_md(correlation)}

## 5. Signal of each number alone

AUC of one number against `label` (0.5 = no signal). Original rows only, no `fixed_code` rows.
Compare every row with the `n_lines` row: that is the length-only baseline (D30).

{_md(signal)}
"""


# ----------------------------------------------------------------------------- command line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--splits-dir", type=Path, default=paths.SPLITS_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out-dir", type=Path, default=paths.CODE_METRICS_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--batch-size", type=int, default=20_000)
    parser.add_argument("--limit", type=int, help="measure only this many functions (trial run)")
    args = parser.parse_args(argv)
    build(
        args.splits_dir,
        args.manifest,
        args.out_dir,
        args.report,
        batch_size=args.batch_size,
        limit=args.limit,
        log=lambda message: print(message, flush=True),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
