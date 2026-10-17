"""
Big-Vul loader.

Outputs
-------
1. data/raw/bigvul_full.parquet
   All 39 raw columns from train.csv, val.csv, and test.csv.

2. data/interim/bigvul.parquet
   Dataset mapped to the unified SHIELD schema.

The raw CSV files are processed in small batches without loading the
complete dataset into memory.

Usage
-----
python -m shield_core.datasets.c_cpp_loaders.bigvul_loader
"""

import os
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from shield_core.datasets.schema import arrow_schema, conform, validate

# ---------------------------------------------------------------------
# Paths and settings
# ---------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]

RAW_DIR = REPO_ROOT / "data" / "raw"
INTERIM_DIR = REPO_ROOT / "data" / "interim"

FULL_PATH = RAW_DIR / "bigvul_full.parquet"
UNIFIED_PATH = INTERIM_DIR / "bigvul.parquet"

KAGGLE_DATASET = "zalinarusinova/bigvul"
SPLITS = ("train", "val", "test")

# Start conservatively because some columns contain very large source
# code and patch strings.
BATCH_ROWS = 128

COMPRESSION = "zstd"

# CSV column name -> unified schema source column name.
COLUMN_ALIASES = {
    "func_before": "func_before",
    "func_after": "func_after",
    "target": "vul",
    "cwe": "CWE ID",
    "project": "project",
    "commit": "commit_id",
    "date": "Publish Date",
    "lang": "lang",
    "cve": "CVE ID",
}


# ---------------------------------------------------------------------
# Kaggle download
# ---------------------------------------------------------------------
def get_dataset_path() -> Path:
    """Use cached Kaggle CSV files if available; download otherwise."""

    import kagglehub

    cache_dir = REPO_ROOT / "data" / "cache" / "kagglehub"
    cache_dir.mkdir(parents=True, exist_ok=True)

    os.environ["KAGGLEHUB_CACHE"] = str(cache_dir.resolve())

    def find_csv_directory() -> Path | None:
        """Find a directory containing all required CSV splits."""

        # kagglehub commonly stores datasets in nested directories.
        if not cache_dir.exists():
            return None

        for train_file in cache_dir.rglob("train.csv"):
            candidate = train_file.parent

            if all((candidate / f"{split}.csv").is_file() for split in SPLITS):
                return candidate

        return None

    dataset_path = find_csv_directory()

    if dataset_path is not None:
        print(f"Using cached Big-Vul CSV files: {dataset_path}")
        return dataset_path

    print(f"Big-Vul CSV files not found in cache. Downloading {KAGGLE_DATASET}...")

    dataset_path = Path(kagglehub.dataset_download(KAGGLE_DATASET))

    missing = [split for split in SPLITS if not (dataset_path / f"{split}.csv").is_file()]

    if missing:
        raise FileNotFoundError(
            f"Missing CSV files after download: {missing}\nDataset path: {dataset_path}"
        )

    print(f"Big-Vul CSV files available: {dataset_path}")

    return dataset_path


# ---------------------------------------------------------------------
# CSV schema
# ---------------------------------------------------------------------


def read_csv_header(csv_path: Path) -> list[str]:
    """Read the CSV header without loading the dataset."""

    with csv_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        import csv

        reader = csv.reader(file)
        try:
            return next(reader)
        except StopIteration as err:
            raise ValueError(f"Empty CSV file: {csv_path}") from err


def build_raw_schema(columns: list[str]) -> pa.Schema:
    """Store every raw CSV column as a nullable Arrow string."""

    return pa.schema([pa.field(column, pa.string(), nullable=True) for column in columns])


# ---------------------------------------------------------------------
# Raw CSV -> full Parquet
# ---------------------------------------------------------------------


def download_raw() -> None:
    """
    Stream all 39 columns from all CSV splits into one Parquet file.

    No usecols filtering is applied: every raw column is retained.
    """

    dataset_path = get_dataset_path()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    tmp_path = FULL_PATH.with_name(FULL_PATH.stem + ".tmp.parquet")

    # Never mistake an incomplete previous attempt for a completed file.
    tmp_path.unlink(missing_ok=True)

    first_csv = dataset_path / f"{SPLITS[0]}.csv"
    columns = read_csv_header(first_csv)

    if len(columns) != len(set(columns)):
        raise ValueError(f"Duplicate column names detected in {first_csv.name}.")

    schema = build_raw_schema(columns)

    print(f"Found {len(columns)} raw columns:")
    print(columns)

    writer = None
    total_rows = 0

    try:
        for split in SPLITS:
            csv_path = dataset_path / f"{split}.csv"

            print(f"\nProcessing {csv_path.name} ...")

            split_columns = read_csv_header(csv_path)

            if split_columns != columns:
                raise ValueError(
                    f"CSV schema mismatch in {csv_path.name}.\n"
                    f"Expected columns: {columns}\n"
                    f"Found columns:    {split_columns}"
                )

            # Explicitly read every column as a string. The block size
            # limits CSV input buffering, while the record batch size
            # limits the number of rows returned per iteration.
            read_options = pacsv.ReadOptions(
                block_size=64 << 20,  # 64 MiB
                use_threads=False,
                encoding="utf8",
            )

            parse_options = pacsv.ParseOptions(
                delimiter=",",
                quote_char='"',
                double_quote=True,
                newlines_in_values=True,
            )

            convert_options = pacsv.ConvertOptions(
                column_types={column: pa.string() for column in columns},
                strings_can_be_null=True,
                quoted_strings_can_be_null=False,
            )

            with pacsv.open_csv(
                csv_path,
                read_options=read_options,
                parse_options=parse_options,
                convert_options=convert_options,
            ) as reader:
                for batch in reader:
                    # Reorder columns if needed and enforce a consistent
                    # schema across all splits.
                    table = pa.Table.from_batches(
                        [batch],
                        schema=reader.schema,
                    )

                    if table.schema.names != columns:
                        table = table.select(columns)

                    # Convert any unexpected schema differences safely.
                    table = table.cast(schema, safe=False)

                    if writer is None:
                        writer = pq.ParquetWriter(
                            tmp_path,
                            schema,
                            compression=COMPRESSION,
                        )

                    writer.write_table(
                        table,
                        row_group_size=BATCH_ROWS,
                    )

                    total_rows += table.num_rows

                    print(
                        f"\rTotal raw rows written: {total_rows:,}",
                        end="",
                        flush=True,
                    )

            print()

        if writer is None:
            raise RuntimeError("No rows were written. The CSV files may be empty.")

        writer.close()
        writer = None

        # Verify the temporary Parquet file before publishing it.
        parquet_file = pq.ParquetFile(tmp_path)

        actual_columns = parquet_file.schema_arrow.names

        if actual_columns != columns:
            raise RuntimeError("Output Parquet columns do not match the source CSV columns.")

        actual_rows = parquet_file.metadata.num_rows

        if actual_rows != total_rows:
            raise RuntimeError(
                f"Row count mismatch: wrote {total_rows:,}, Parquet contains {actual_rows:,}."
            )

        # Replace the old output only after successful completion.
        tmp_path.replace(FULL_PATH)

    except Exception:
        if writer is not None:
            writer.close()

        tmp_path.unlink(missing_ok=True)
        raise

    print("\nRaw Big-Vul saved successfully.")
    print(f"Rows:    {total_rows:,}")
    print(f"Columns: {len(columns)}")
    print(f"Path:    {FULL_PATH.relative_to(REPO_ROOT)}")


# ---------------------------------------------------------------------
# Raw Parquet -> unified schema
# ---------------------------------------------------------------------


def map_to_unified(raw: pd.DataFrame) -> pd.DataFrame:
    """Map the selected raw columns into the unified schema."""

    aliases = COLUMN_ALIASES

    target = pd.to_numeric(
        raw[aliases["target"]],
        errors="coerce",
    ).fillna(0)

    is_vulnerable = target.eq(1)

    out = pd.DataFrame(index=raw.index)

    # Use vulnerable code for positive samples,
    # and fixed code for non-vulnerable samples.
    out["code"] = raw[aliases["func_before"]].where(
        is_vulnerable,
        raw[aliases["func_after"]],
    )

    out["fixed_code"] = raw[aliases["func_after"]].where(
        is_vulnerable,
        None,
    )

    out["language"] = raw[aliases["lang"]].fillna("c")

    out["label"] = is_vulnerable.astype("int64")

    out["cwe"] = raw[aliases["cwe"]]

    # Keep missing project/commit as <NA> (schema contract); "unknown" would merge
    # unrelated rows into one fake project and break group-based splits.
    out["project"] = raw[aliases["project"]]

    out["commit"] = raw[aliases["commit"]]

    date_column = aliases["date"]

    if date_column in raw.columns:
        out["date"] = pd.to_datetime(
            raw[date_column],
            errors="coerce",
        ).dt.strftime("%Y-%m-%d")
    else:
        out["date"] = None

    out["cve"] = raw[aliases["cve"]]

    return out.reset_index(drop=True)


def build_unified() -> None:
    """
    Read only the required columns from raw Parquet and build the
    unified dataset.

    The raw Parquet remains intact with all original columns.
    """

    if not FULL_PATH.is_file():
        raise FileNotFoundError(f"Raw Parquet does not exist: {FULL_PATH}")

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)

    tmp_path = UNIFIED_PATH.with_name(UNIFIED_PATH.stem + ".tmp.parquet")

    tmp_path.unlink(missing_ok=True)

    available_columns = pq.ParquetFile(FULL_PATH).schema_arrow.names

    required_columns = list(COLUMN_ALIASES.values())

    missing = [column for column in required_columns if column not in available_columns]

    if missing:
        raise ValueError(f"Required columns are missing from raw Parquet: {missing}")

    raw_file = pq.ParquetFile(FULL_PATH)

    writer = None
    total_rows = 0
    label_counts = {0: 0, 1: 0}
    null_cwe = 0
    null_date = 0
    null_cve = 0

    try:
        for batch in raw_file.iter_batches(
            batch_size=BATCH_ROWS,
            columns=required_columns,
            use_threads=False,
        ):
            raw = batch.to_pandas()

            mapped = map_to_unified(raw)
            unified = conform(mapped, "bigvul")

            problems = validate(unified)

            if problems:
                raise ValueError(
                    "Unified Big-Vul failed validation:\n  - " + "\n  - ".join(map(str, problems))
                )

            # Explicit schema keeps cwe/cve as list<string> in every batch.
            table = pa.Table.from_pandas(
                unified,
                schema=arrow_schema(),
                preserve_index=False,
            )

            if writer is None:
                writer = pq.ParquetWriter(
                    tmp_path,
                    table.schema,
                    compression=COMPRESSION,
                )

            writer.write_table(
                table,
                row_group_size=BATCH_ROWS,
            )

            total_rows += len(unified)

            counts = unified["label"].value_counts()

            for label in (0, 1):
                label_counts[label] += int(counts.get(label, 0))

            # cwe/cve are lists, so "missing" means an empty list (isna() is always False).
            null_cwe += int(unified["cwe"].map(len).eq(0).sum())
            null_date += int(unified["date"].isna().sum())
            null_cve += int(unified["cve"].map(len).eq(0).sum())

            print(
                f"\rUnified rows written: {total_rows:,}",
                end="",
                flush=True,
            )

        if writer is None:
            raise RuntimeError("No unified rows were written.")

        writer.close()
        writer = None

        tmp_path.replace(UNIFIED_PATH)

    except Exception:
        if writer is not None:
            writer.close()

        tmp_path.unlink(missing_ok=True)
        raise

    print("\n\n--- Big-Vul summary ---")
    print(f"Raw rows:       {raw_file.metadata.num_rows:,}")
    print(f"Raw columns:    {len(available_columns)}")
    print(f"Unified rows:   {total_rows:,}")
    print(f"Label balance:  {label_counts}")
    print(f"Null CWE rows:  {null_cwe:,}")
    print(f"Null date rows: {null_date:,}")
    print(f"Null CVE rows:  {null_cve:,}")
    print("Validation:     OK")
    print(f"Raw output:     {FULL_PATH.relative_to(REPO_ROOT)}")
    print(f"Unified output: {UNIFIED_PATH.relative_to(REPO_ROOT)}")


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------


def main() -> int:
    # Build the full raw Parquet only when it does not exist.
    if FULL_PATH.exists():
        print(
            "Raw Big-Vul Parquet already exists; "
            f"skipping raw conversion: {FULL_PATH.relative_to(REPO_ROOT)}"
        )
    else:
        download_raw()

    # Build the unified dataset.
    build_unified()

    return 0


if __name__ == "__main__":
    sys.exit(main())
