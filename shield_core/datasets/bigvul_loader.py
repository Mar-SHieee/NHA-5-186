"""
Big-Vul loader.

Usage (run from the repository root):
    python -m shield_core.datasets.bigvul_loader

What it does:
    1. Downloads Big-Vul from Hugging Face (only if the raw file is missing)
       and saves it unchanged to      data/interim/bigvul_full.parquet
    2. Maps the raw columns into the unified 8-column schema
    3. Runs conform() and validate() from schema.py
    4. Saves the unified dataset to   data/interim/bigvul.parquet
"""

import sys
from pathlib import Path

import pandas as pd

from shield_core.datasets.schema import conform, validate

# ----------------------------------------------------------------------
# Paths (parents[2] = repository root, wherever the command is run from)
# ----------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
INTERIM_DIR = REPO_ROOT / "data" / "interim"
FULL_PATH = INTERIM_DIR / "bigvul_full.parquet"  # raw, unchanged
UNIFIED_PATH = INTERIM_DIR / "bigvul.parquet"  # unified 8-column schema

HF_DATASET = "bstee615/bigvul"

# Raw columns the mapping depends on
REQUIRED_RAW_COLUMNS = [
    "func_before",
    "func_after",
    "lang",
    "vul",
    "CWE ID",
    "project",
    "commit_id",
]


def download_raw() -> None:
    """Download Big-Vul, merge all splits, save the raw data unchanged."""
    # Imported here so the "already exists" path doesn't need `datasets` loaded.
    from datasets import load_dataset

    print(f"Downloading Big-Vul from Hugging Face ({HF_DATASET})...")
    splits = load_dataset(HF_DATASET)  # DatasetDict: train / validation / test

    # Merge every available split into one dataframe.
    frames = [splits[name].to_pandas() for name in splits]
    raw = pd.concat(frames, ignore_index=True)

    # Write to a temporary file first, then rename, so a failed write
    # never leaves a corrupted bigvul_full.parquet behind.
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = FULL_PATH.with_suffix(".parquet.tmp")
    try:
        raw.to_parquet(tmp_path, index=False)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    tmp_path.replace(FULL_PATH)
    print(f"Saved raw Big-Vul ({len(raw):,} rows) to {FULL_PATH.relative_to(REPO_ROOT)}")


def map_to_unified(raw: pd.DataFrame) -> pd.DataFrame:
    """Map raw Big-Vul columns to the unified schema columns (raw is not modified)."""
    missing = [c for c in REQUIRED_RAW_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"Big-Vul is missing expected columns: {missing}")

    is_vul = raw["vul"].astype(int) == 1

    out = pd.DataFrame(index=raw.index)

    # vul = 1 -> code is the vulnerable function (func_before), fixed_code the patched one.
    # vul = 0 -> func_before is NULL by design, so code is func_after and there is no fix.
    out["code"] = raw["func_before"].where(is_vul, raw["func_after"])
    out["fixed_code"] = raw["func_after"].where(is_vul, pd.NA)

    out["language"] = raw["lang"]
    out["label"] = raw["vul"].astype(int)
    out["cwe"] = raw["CWE ID"]  # normalized by conform() -> normalize_cwe()
    out["project"] = raw["project"]
    out["commit"] = raw["commit_id"]

    return out


def main() -> int:
    # Step 1-3: download the raw dataset only if we don't already have it.
    if FULL_PATH.exists():
        print(f"Raw Big-Vul already exists, skipping download: {FULL_PATH.relative_to(REPO_ROOT)}")
    else:
        download_raw()

    # Step 4: read the raw dataframe.
    raw = pd.read_parquet(FULL_PATH)

    # Step 5-6: map, then conform to the unified schema (conform adds `source`).
    mapped = map_to_unified(raw)
    unified = conform(mapped, "bigvul")

    # Step 7: validate.
    problems = validate(unified)
    if problems:
        raise ValueError(
            "Unified Big-Vul failed validation:\n  - " + "\n  - ".join(map(str, problems))
        )

    # Step 8: save.
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    unified.to_parquet(UNIFIED_PATH, index=False)

    # Step 9: summary.
    n_vul = int((unified["label"] == 1).sum())
    n_clean = int((unified["label"] == 0).sum())
    print("\n--- Big-Vul summary ---")
    print(f"Raw rows:        {len(raw):,}")
    print(f"Unified rows:    {len(unified):,}")
    print(f"  Vulnerable:    {n_vul:,}")
    print(f"  Non-vulnerable:{n_clean:,}")
    print(f"Raw output:      {FULL_PATH.relative_to(REPO_ROOT)}")
    print(f"Unified output:  {UNIFIED_PATH.relative_to(REPO_ROOT)}")
    print("Validation:      OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
