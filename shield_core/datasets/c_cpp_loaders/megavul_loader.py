"""MegaVul loader (W1-P1-01). Streams the raw JSON so the whole file never sits in memory."""

from __future__ import annotations

from collections import Counter
from itertools import islice
from pathlib import Path, PurePosixPath

import ijson
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from shield_core.datasets.schema import conform, validate


def batched(iterable, n):
    """Batch data into tuples of length n. Last batch may be shorter."""
    if n < 1:
        raise ValueError("n must be at least one")

    iterator = iter(iterable)

    while True:
        batch = tuple(islice(iterator, n))

        if not batch:
            return

        yield batch


PROJECT_ROOT = Path(__file__).resolve().parents[2]

SOURCE = "megavul"
DEFAULT_PATH = PROJECT_ROOT / "data" / "raw" / "megavul_simple.json"
DEFAULT_OUT = PROJECT_ROOT / "data" / "interim" / "megavul.parquet"

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
        "cwe": cwe_ids if cwe_ids else None,
        "project": rec.get("repo_name"),
        "commit": rec.get("commit_hash"),
        # "date": not available in MegaVul -> conform() fills it with NaT
        "fixed_code": rec.get("func") if is_vul else None,
    }


def _stream_rows(path: Path, limit: int | None, stats: Counter):
    """Yield mapped rows one by one, counting skipped and multi-CWE records."""
    records = _iter_records(path)

    if limit is not None:
        records = islice(records, limit)

    for rec in records:
        row = _to_row(rec)

        if row is None:
            stats["skipped_unknown_language"] += 1
            continue

        if len(rec.get("cwe_ids") or []) > 1:
            stats["records_with_multiple_cwes"] += 1

        yield row


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


def megavul_to_parquet(
    path: str | Path = DEFAULT_PATH,
    out_path: str | Path = DEFAULT_OUT,
    chunk_size: int = 20_000,
    limit: int | None = None,
) -> dict:
    """Stream MegaVul -> unified schema -> parquet."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = out_path.with_name(out_path.name + ".tmp")

    stats: Counter = Counter()
    by_language = pd.DataFrame(
        columns=["count", "vulnerable"],
        dtype="int64",
    )
    cwe_counts: Counter = Counter()
    projects: set[str] = set()

    writer = None
    schema = None

    try:
        rows = _stream_rows(Path(path), limit, stats)

        for i, chunk in enumerate(batched(rows, chunk_size)):
            df = conform(pd.DataFrame(chunk), SOURCE)

            problems = validate(df)
            if problems:
                raise ValueError(f"chunk {i} failed validation: {problems}")

            table = pa.Table.from_pandas(
                df,
                schema=schema,
                preserve_index=False,
            )

            if writer is None:
                schema = table.schema
                writer = pq.ParquetWriter(
                    tmp_path,
                    schema,
                    compression="zstd",
                )

            writer.write_table(table)

            vul = df[df["label"] == 1]

            stats["rows"] += len(df)
            stats["vulnerable"] += len(vul)
            stats["vulnerable_missing_cwe"] += int(vul["cwe"].apply(lambda x: len(x) == 0).sum())

            cwe_counts.update(vul["cwe"].explode().dropna().value_counts().to_dict())

            chunk_lang = df.groupby("language")["label"].agg(
                count="count",
                vulnerable="sum",
            )

            by_language = by_language.add(
                chunk_lang,
                fill_value=0,
            )

            projects.update(df["project"].dropna().unique())

            print(
                f"[megavul] chunk {i}: total rows so far = {stats['rows']}",
                flush=True,
            )

    finally:
        if writer is not None:
            writer.close()

    if writer is None:
        raise ValueError("no usable MegaVul records found")

    tmp_path.replace(out_path)

    summary = dict(stats)
    summary["projects"] = len(projects)

    print(f"\n[megavul] wrote {out_path}")
    print(summary)

    print("\nby language (count, vulnerable):")
    print(by_language.astype("int64"))

    print("\ntop 15 CWEs among vulnerable rows:")
    print(pd.Series(cwe_counts).sort_values(ascending=False).head(15))

    return summary


if __name__ == "__main__":
    megavul_to_parquet()
