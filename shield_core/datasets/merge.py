"""Merge the deduped interim datasets into one table in the unified schema (W2-P1-01).

Only files that exist are merged; missing ones are skipped. Every existing file is
checked against `schema.validate` before it is used, and the `source` column of each
row is kept exactly as the loader wrote it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

try:  # normal case: imported as part of the shield_core package
    from . import schema
except ImportError:  # run as a plain script
    import schema  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[2]
INTERIM_DIR = REPO_ROOT / "data" / "interim"
MERGED_NAME = "merged_datasets.parquet"

# Expected deduped files (whichever exist are used).
DATASET_FILES = [
    "bigvul_deduped.parquet",
    "megavul_deduped.parquet",
    "zenodo_python_deduped_fixed.parquet",
    "cvefixes_python_deduped_fixed.parquet",
]


class DatasetSchemaError(ValueError):
    """An existing dataset file does not follow the unified schema."""


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_dataset(path: Path) -> pd.DataFrame:
    """Read one deduped parquet file and verify it against the unified schema."""
    present = pq.read_schema(path).names
    missing = [c for c in schema.COLUMNS if c not in present]
    if missing:
        raise DatasetSchemaError(
            f"{path.name}: missing columns {missing} (schema {schema.SCHEMA_VERSION}); "
            "regenerate it with the current loader"
        )
    df = schema.from_parquet(path)  # restores list columns, enforces dtypes
    problems = schema.validate(df)
    if problems:
        shown = "; ".join(problems[:5])
        raise DatasetSchemaError(f"{path.name}: {len(problems)} schema problems, e.g. {shown}")
    return df


def merge_datasets(
    interim_dir: Path = INTERIM_DIR,
    filenames: list[str] = DATASET_FILES,
    verbose: bool = True,
) -> tuple[pd.DataFrame, list[dict]]:
    """Return (merged DataFrame, per-file info). Raises FileNotFoundError if nothing exists."""
    interim_dir = Path(interim_dir)
    frames, inputs = [], []
    for name in filenames:
        path = interim_dir / name
        if not path.exists():
            if verbose:
                print(f"  skip (not found): {name}")
            continue
        df = load_dataset(path)
        frames.append(df)
        inputs.append(
            {
                "file": name,
                "rows": int(len(df)),
                "sha256": file_sha256(path),
                "sources": sorted(df["source"].unique().tolist()),
            }
        )
        if verbose:
            print(f"  loaded: {name} ({len(df):,} rows)")
    if not frames:
        raise FileNotFoundError(f"none of {filenames} found in {interim_dir}")
    merged = pd.concat(frames, ignore_index=True)[schema.COLUMNS].astype(schema.DTYPES)
    return merged, inputs


def count_cross_source_duplicates(df: pd.DataFrame) -> int:
    """Number of whitespace-insensitive code strings that appear in more than one source.

    Dedupe should already have removed these; a non-zero value means it was not applied
    across datasets. Reported only, never dropped here.
    """
    key = pd.util.hash_pandas_object(
        df["code"].astype(object).str.replace(r"\s+", "", regex=True), index=False
    )
    return int((pd.DataFrame({"k": key, "s": df["source"]}).groupby("k")["s"].nunique() > 1).sum())


def remove_cross_source_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Remove code duplicates across sources, keeping the first occurrence."""
    normalized_code = df["code"].astype("string").str.replace(r"\s+", "", regex=True)

    duplicated = normalized_code.duplicated(keep="first")
    removed = int(duplicated.sum())

    if removed:
        print(f"  Removed {removed:,} cross-source duplicate rows")

    return df.loc[~duplicated].reset_index(drop=True)


def merge_deduped_datasets(
    interim_dir: Path = INTERIM_DIR, output_path: Path | None = None
) -> pd.DataFrame | None:
    """Merge available deduped datasets and write `merged_datasets.parquet`."""
    interim_dir = Path(interim_dir)
    print(f"Searching for deduped datasets in {interim_dir} ...")
    try:
        merged, _ = merge_datasets(interim_dir)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        return None
    dups = count_cross_source_duplicates(merged)
    if dups:
        print(f"  WARNING: {dups:,} code strings appear in more than one source (dedupe gap)")
    output_path = Path(output_path) if output_path else interim_dir / MERGED_NAME
    schema.to_parquet(merged, output_path)
    print(f"Merged {len(merged):,} rows -> {output_path}")
    return merged


if __name__ == "__main__":
    merge_deduped_datasets()
