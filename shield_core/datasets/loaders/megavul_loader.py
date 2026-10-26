"""MegaVul loader (W1-P1-01). Streams the raw JSON so the whole file never sits in memory."""

from __future__ import annotations

import re
from collections import Counter
from itertools import islice
from pathlib import Path, PurePosixPath

import ijson
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from shield_core.datasets.project_names import project_from_repo_url
from shield_core.datasets.schema import arrow_schema, conform, validate


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


PROJECT_ROOT = Path(__file__).resolve().parents[3]

SOURCE = "megavul"
DEFAULT_PATH = PROJECT_ROOT / "data" / "raw" / "megavul.json"
DEFAULT_OUT = PROJECT_ROOT / "data" / "interim" / "megavul.parquet"
MAPPING_SUFFIX = (
    "_commit_cve_mapping.parquet"  # megavul.parquet -> megavul_commit_cve_mapping.parquet
)
HF_DATASET_KAGGLE = "marcdamie/megavul-a-cc-java-vulnerability-dataset"  # [cite: 2]

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


def download_raw() -> None:
    """Download MegaVul from Kaggle and copy megavul.json to DEFAULT_PATH."""
    import os
    import shutil

    import kagglehub

    cache_dir = PROJECT_ROOT / "data" / "cache" / "kagglehub"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["KAGGLEHUB_CACHE"] = str(cache_dir.resolve())

    print(f"Downloading MegaVul from Kaggle ({HF_DATASET_KAGGLE})...")
    dataset_path = Path(kagglehub.dataset_download(HF_DATASET_KAGGLE))

    source_json = dataset_path / "megavul" / "c_cpp" / "megavul.json"

    if not source_json.exists():
        found_files = list(dataset_path.glob("**/megavul.json"))
        found_files = [f for f in found_files if f.name == "megavul.json"]
        if found_files:
            source_json = found_files[0]
        else:
            raise FileNotFoundError(
                f"Could not find megavul.json in downloaded dataset at {dataset_path}"
            )

    DEFAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source_json, DEFAULT_PATH)
    print(f"Saved raw MegaVul JSON to {DEFAULT_PATH.relative_to(PROJECT_ROOT)}")


def _iter_records(path: Path):
    """Yield records one at a time. Handles a top-level JSON array or JSON-lines."""
    with open(path, "rb") as f:
        head = f.read(64).lstrip()
        f.seek(0)
        if head.startswith(b"["):
            yield from ijson.items(f, "item")
        else:  # concatenated / line-delimited objects
            yield from ijson.items(f, "", multiple_values=True)


def _project(rec: dict) -> object:
    """`owner/repo` from the record's `git_url`; falls back to `repo_name` as written.

    `git_url` may be a commit URL, so only GitHub URLs are used (their first two path
    segments are always owner/repo). Other hosts would give "host/.../commit/<sha>", which
    is not a project name, so they fall back to `repo_name`.
    """
    name = project_from_repo_url(rec.get("git_url"), github_only=True)
    return rec.get("repo_name") if pd.isna(name) else name


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
        "project": _project(rec),
        "commit": rec.get("commit_hash"),
        "date": rec.get("publish_date"),  # MegaVul has no `date` field
        "cve": rec.get("cve_id"),
        "fixed_code": rec.get("func") if is_vul else None,
    }


_CVE_PATTERN = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)


def _add_commit_cve_pairs(rec: dict, pairs: set[tuple[str, str]]) -> None:
    """Add this record's (commit, CVE) links to `pairs`.

    Uses every record, including the ones skipped later for an unknown language, so the
    mapping keeps the complete relation. CVE ids are extracted with a regex instead of
    assuming the field holds exactly one id.
    """
    commit_value, cve_value = rec.get("commit_hash"), rec.get("cve_id")
    if commit_value is None or cve_value is None:
        return
    commit = str(commit_value).strip()
    if not commit:
        return
    for cve in _CVE_PATTERN.findall(str(cve_value).upper()):
        pairs.add((commit, cve))


def save_commit_cve_mapping(pairs: set[tuple[str, str]], path: Path) -> int:
    """Write distinct commit-CVE associations, separately from the code samples.

    One row per distinct pair (columns `commit`, `cve`). It does not claim that every CVE
    associated with a commit affects every changed function.
    """
    path = Path(path)
    mapping = pd.DataFrame(sorted(pairs), columns=["commit", "cve"])
    mapping = mapping.astype({"commit": "string", "cve": "string"})

    tmp_path = path.with_name(path.stem + ".tmp.parquet")
    tmp_path.unlink(missing_ok=True)
    try:
        mapping.to_parquet(tmp_path, index=False, compression="zstd")
        # Check the temporary file before replacing any previous mapping.
        check = pq.ParquetFile(tmp_path)
        try:
            if check.schema_arrow.names != ["commit", "cve"]:
                raise RuntimeError("Commit-CVE mapping has an unexpected schema.")
            if check.metadata.num_rows != len(mapping):
                raise RuntimeError("Commit-CVE mapping row count verification failed.")
        finally:
            check.close()
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return len(mapping)


def _stream_rows(
    path: Path,
    limit: int | None,
    stats: Counter,
    pairs: set[tuple[str, str]] | None = None,
):
    """Yield mapped rows one by one, counting skipped and multi-CWE records.

    If `pairs` is given, every record's (commit, CVE) links are collected into it.
    """
    records = _iter_records(path)

    if limit is not None:
        records = islice(records, limit)

    for rec in records:
        if pairs is not None:
            _add_commit_cve_pairs(rec, pairs)

        row = _to_row(rec)

        if row is None:
            stats["skipped_unknown_language"] += 1
            continue

        if len(rec.get("cwe_ids") or []) > 1:
            stats["records_with_multiple_cwes"] += 1

        yield row


def load_megavul(path: str | Path = DEFAULT_PATH, limit: int | None = None) -> pd.DataFrame:
    """Load MegaVul into the unified schema. Use `limit` to try a few records first."""
    path = Path(path)
    if not path.exists():
        download_raw()

    records = _iter_records(path)
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
    mapping_path: str | Path | None = None,
) -> dict:
    """Stream MegaVul -> unified schema -> parquet, plus a commit-CVE mapping parquet.

    The mapping goes next to `out_path` as `<name>_commit_cve_mapping.parquet` unless
    `mapping_path` is given. With `limit`, both files only cover the first `limit` records.
    """
    path = Path(path)
    if not path.exists():
        download_raw()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mapping_path = (
        Path(mapping_path) if mapping_path else out_path.with_name(out_path.stem + MAPPING_SUFFIX)
    )
    pairs: set[tuple[str, str]] = set()

    tmp_path = out_path.with_name(out_path.name + ".tmp")

    stats: Counter = Counter()
    by_language = pd.DataFrame(
        columns=["count", "vulnerable"],
        dtype="int64",
    )
    cwe_counts: Counter = Counter()
    projects: set[str] = set()

    writer = None
    # Fixed schema: inferring it from chunk 0 gives list<null> when that chunk has no CWE/CVE.
    schema = arrow_schema()

    try:
        rows = _stream_rows(path, limit, stats, pairs)

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
    summary["commit_cve_links"] = save_commit_cve_mapping(pairs, mapping_path)

    print(f"\n[megavul] wrote {out_path}")
    print(f"[megavul] wrote {mapping_path} ({summary['commit_cve_links']:,} commit-CVE links)")
    print(summary)

    print("\nby language (count, vulnerable):")
    print(by_language.astype("int64"))

    print("\ntop 15 CWEs among vulnerable rows:")
    print(pd.Series(cwe_counts).sort_values(ascending=False).head(15))

    return summary


if __name__ == "__main__":
    megavul_to_parquet()
