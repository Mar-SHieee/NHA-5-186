"""MegaVul loader (W1-P1-01). Streams the raw JSON so the whole file never sits in memory."""

from __future__ import annotations

import sys
from itertools import islice
from pathlib import Path, PurePosixPath

import ijson
import pandas as pd

from shield_core.datasets.schema import conform, validate

SOURCE = "megavul"
DEFAULT_PATH = Path("data/raw/megavul_simple.json")

# Language is not a MegaVul field; it is derived from the extension of file_path.
# Extensions not listed here are skipped (never guessed).
_EXT_TO_LANGUAGE = {
    ".c": "cpp",
    ".h": "cpp",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".java": "java",
}


def _language(file_path: str | None) -> str | None:
    if not file_path:
        return None
    return _EXT_TO_LANGUAGE.get(PurePosixPath(file_path).suffix.lower())


def _iter_records(path: Path):
    """Yield records one at a time. Handles a top-level JSON array or JSON-lines."""
    with open(path, "rb") as f:
        head = f.read(64).lstrip()
        f.seek(0)
        if head.startswith(b"["):
            yield from ijson.items(f, "item")
        else:  # concatenated / line-delimited objects
            yield from ijson.items(f, "", multiple_values=True)


def _to_row(rec: dict) -> dict | None:
    """Map one MegaVul record to schema columns. Returns None if language is unknown."""
    language = _language(rec.get("file_path"))
    if language is None:
        return None

    is_vul = bool(rec["is_vul"])
    cwe_ids = rec.get("cwe_ids") or []

    return {
        "code": rec.get("func_before") if is_vul else rec.get("func"),
        "language": language,
        "label": int(is_vul),
        "cwe": cwe_ids[0] if cwe_ids else None,  # first CWE only (documented rule)
        "project": rec.get("repo_name"),
        "commit": rec.get("commit_hash"),
        # "date": not available in MegaVul -> conform() fills it with NaT
        "fixed_code": rec.get("func") if is_vul else None,
    }


def load_megavul(path: str | Path = DEFAULT_PATH, limit: int | None = None) -> pd.DataFrame:
    """Load MegaVul into the unified schema. Use `limit` to try a few records first."""
    records = _iter_records(Path(path))
    if limit is not None:
        records = islice(records, limit)

    rows, skipped, multi_cwe = [], 0, 0
    for rec in records:
        row = _to_row(rec)
        if row is None:
            skipped += 1
            continue
        if len(rec.get("cwe_ids") or []) > 1:
            multi_cwe += 1
        rows.append(row)

    df = conform(pd.DataFrame(rows), SOURCE)
    problems = validate(df)
    if problems:
        raise ValueError(f"MegaVul failed validation: {problems}")

    print(
        f"[megavul] rows={len(df)} skipped_unknown_language={skipped} "
        f"records_with_multiple_cwes={multi_cwe}"
    )
    return df


if __name__ == "__main__":
    # Try a few records first:  python -m shield_core.datasets.megavul 5
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    sample = load_megavul(limit=n)
    pd.set_option("display.max_colwidth", 60)
    print(sample.dtypes)
    print(sample.drop(columns=["code", "fixed_code"]))
    print("\ncode[0] (first 300 chars):\n", sample.loc[0, "code"][:300])
    print("\nfixed_code[0] (first 300 chars):\n", sample.loc[0, "fixed_code"][:300])
