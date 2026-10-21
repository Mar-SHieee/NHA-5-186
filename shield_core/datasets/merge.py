"""Merge the deduped interim datasets into one table in the unified schema (W2-P1-01).

Generic: every `*_deduped.parquet` file found in the interim directory is merged, so a new
dataset only needs its loader + dedupe step, never an edit here. Every file is checked
against `schema.validate` before it is used, and the `source` column of each row is kept
exactly as the loader wrote it.

Run:  python -m shield_core.datasets.merge [--interim-dir DIR] [--output FILE] [--only NAME ...]
"""

from __future__ import annotations

import argparse
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
DEDUPED_GLOB = "*_deduped.parquet"  # what dedupe.py writes, one file per dataset


class DatasetSchemaError(ValueError):
    """An existing dataset file does not follow the unified schema."""


def discover_datasets(interim_dir: Path = INTERIM_DIR) -> list[str]:
    """Names of all deduped files in `interim_dir`, sorted so the merge is deterministic."""
    return sorted(p.name for p in Path(interim_dir).glob(DEDUPED_GLOB) if p.name != MERGED_NAME)


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
    filenames: list[str] | None = None,
    verbose: bool = True,
) -> tuple[pd.DataFrame, list[dict]]:
    """Return (merged DataFrame, per-file info).

    `filenames=None` (default) merges every `*_deduped.parquet` in `interim_dir`.
    Raises FileNotFoundError if nothing is found, DatasetSchemaError on a bad file or when
    the same `source` value appears in two files (that would mean a stale/duplicate file).
    """
    interim_dir = Path(interim_dir)
    names = discover_datasets(interim_dir) if filenames is None else list(filenames)
    frames, inputs, seen_sources = [], [], {}
    for name in names:
        path = interim_dir / name
        if not path.exists():
            raise FileNotFoundError(f"requested dataset not found: {path}")
        df = load_dataset(path)
        sources = sorted(df["source"].unique().tolist())
        for s in sources:
            if s in seen_sources:
                raise DatasetSchemaError(
                    f"source '{s}' appears in both {seen_sources[s]} and {name}; "
                    "remove the stale file"
                )
            seen_sources[s] = name
        frames.append(df)
        inputs.append(
            {"file": name, "rows": int(len(df)), "sha256": file_sha256(path), "sources": sources}
        )
        if verbose:
            print(f"  loaded: {name} ({len(df):,} rows, sources={sources})")
    if not frames:
        raise FileNotFoundError(f"no '{DEDUPED_GLOB}' files found in {interim_dir}")
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


def merge_deduped_datasets(
    interim_dir: Path = INTERIM_DIR,
    output_path: Path | None = None,
    filenames: list[str] | None = None,
) -> pd.DataFrame | None:
    """Merge the deduped datasets and write `merged_datasets.parquet`."""
    interim_dir = Path(interim_dir)
    print(f"Searching for '{DEDUPED_GLOB}' in {interim_dir} ...")
    try:
        merged, _ = merge_datasets(interim_dir, filenames)
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


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--interim-dir", type=Path, default=INTERIM_DIR)
    p.add_argument("--output", type=Path, default=None)
    p.add_argument(
        "--only",
        nargs="+",
        metavar="FILE",
        help="merge only these file names (default: every *_deduped.parquet)",
    )
    a = p.parse_args(argv)
    merge_deduped_datasets(a.interim_dir, a.output, a.only)


if __name__ == "__main__":
    main()
