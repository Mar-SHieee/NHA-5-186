"""Load Zenodo data_Python.csv into SHIELD's unified 10-column schema (v1.2).

From the repository root:
    python -m shield_core.datasets.loaders.zenodo_python_loader

Optional GitHub commit enrichment (uses GitHub API; may be rate limited):
    python -m shield_core.datasets.loaders.zenodo_python_loader --resolve-commits

Set GITHUB_TOKEN in your environment to increase the API rate limit.

Outputs (both are OVERWRITTEN if they already exist):
    data/interim/zenodo_python.parquet                       unified-schema table
    data/interim/zenodo_python_commit_cve_mapping.parquet    project / commit / date / cve links

No deduplication is performed.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd

from shield_core.datasets.project_names import project_from_repo_url
from shield_core.datasets.schema import COLUMNS, conform, to_parquet, validate

SOURCE = "zenodo_13870382_python"
ZENODO_URL = "https://zenodo.org/records/13870382/files/data_Python.csv?download=1"
DEFAULT_INPUT = Path("data/raw/zenodo_python/data_Python.csv")
DEFAULT_OUTPUT = Path("data/interim/zenodo_python.parquet")
DEFAULT_MAPPING = Path("data/interim/zenodo_python_commit_cve_mapping.parquet")
DEFAULT_CACHE = Path("data/cache/zenodo_python_commit_cache.json")
REQUIRED_INPUT_COLUMNS = {
    "vul_code",
    "is_vulnerable",
    "repo_url",
    "cwe_id",
    "patch",
    "committer_date",
    "cve_id",
}
MAPPING_COLUMNS = ["project", "commit", "date", "cve"]

# Cached lookup results with these statuses are retried on the next run.
RETRYABLE_STATUSES = {
    "rate_limited",
    "network_error",
    "http_401",
    "http_403",
    "http_429",
    "http_500",
    "http_502",
    "http_503",
    "http_504",
    "unexpected_response",
    "search_truncated",
}


def _ensure_raw_csv(path: Path, url: str = ZENODO_URL) -> None:
    """Download raw CSV from Zenodo if it is missing locally."""
    if path.exists():
        return
    print(f"Downloading {url} -> {path} ...")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".csv.part")
    request = Request(url, headers={"User-Agent": "SHIELD-dataset-loader"})
    with urlopen(request, timeout=300) as response, tmp_path.open("wb") as out_file:
        shutil.copyfileobj(response, out_file)
    tmp_path.replace(path)


def _github_json(url: str, token: str | None) -> object:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "SHIELD-commit-enrichment"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=25) as response:
        return json.load(response)


def _commit_lookup(project: str, date: str, message: str, token: str | None) -> dict:
    """Find exact repository + commit-message + committer-timestamp matches.

    Returns an SHA only for a unique match; never guesses. This does not prove
    the commit is the original security fix (it may be a merge commit).
    """
    timestamp = pd.to_datetime(date, utc=True, errors="coerce")
    if pd.isna(timestamp) or not message.strip():
        return {"sha": None, "status": "missing_metadata"}

    # API 'since'/'until' restrict by commit timestamps; a 48-hour window
    # tolerates small differences in author/committer timestamps.
    since = (timestamp - timedelta(days=2)).isoformat().replace("+00:00", "Z")
    until = (timestamp + timedelta(days=2)).isoformat().replace("+00:00", "Z")
    expected = message.strip().replace("\r\n", "\n")
    matches = set()
    try:
        for page in range(1, 6):
            url = (
                f"https://api.github.com/repos/{quote(project, safe='/')}/commits"
                f"?since={quote(since)}&until={quote(until)}&per_page=100&page={page}"
            )
            entries = _github_json(url, token)
            if not isinstance(entries, list):
                return {"sha": None, "status": "unexpected_response"}
            for entry in entries:
                details = entry.get("commit") or {}
                msg = (details.get("message") or "").strip().replace("\r\n", "\n")
                committed = (details.get("committer") or {}).get("date")
                actual_date = pd.to_datetime(committed, utc=True, errors="coerce")
                if (
                    msg == expected
                    and pd.notna(actual_date)
                    and abs(actual_date - timestamp) <= timedelta(minutes=1)
                ):
                    matches.add(entry["sha"])
            if len(entries) < 100:
                break
        else:
            # The window contained >500 commits; absence of a match is not conclusive.
            if not matches:
                return {"sha": None, "status": "search_truncated"}
    except HTTPError as exc:
        if exc.code in (403, 429):
            return {"sha": None, "status": "rate_limited"}
        return {"sha": None, "status": f"http_{exc.code}"}
    except (URLError, TimeoutError, OSError):
        return {"sha": None, "status": "network_error"}

    if len(matches) == 1:
        return {"sha": next(iter(matches)), "status": "exact_message_and_timestamp"}
    if len(matches) > 1:
        return {"sha": None, "status": "ambiguous"}
    return {"sha": None, "status": "not_found"}


def enrich_commits(raw: pd.DataFrame, cache_path: Path, token: str | None) -> pd.Series:
    """Use cached lookups; query once per distinct repo/date/message combination."""
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    resolved = []
    unique = {}
    for repo, date, message in zip(
        raw["repo_url"], raw["committer_date"], raw["commit_msg"], strict=False
    ):
        # GitHub API lookups only make sense for GitHub repositories.
        project = project_from_repo_url(repo, github_only=True)
        key = json.dumps(
            [
                None if pd.isna(project) else project,
                None if pd.isna(date) else str(date),
                None if pd.isna(message) else str(message),
            ],
            ensure_ascii=False,
        )
        resolved.append(key)
        unique[key] = (project, date, message)

    print(f"Unique repo/date/message lookups: {len(unique):,}")

    for n, (key, (project, date, message)) in enumerate(unique.items(), 1):
        if key in cache and cache[key].get("status") not in RETRYABLE_STATUSES:
            continue
        if pd.isna(project) or pd.isna(date) or pd.isna(message):
            result = {"sha": None, "status": "missing_metadata"}
        else:
            result = _commit_lookup(str(project), str(date), str(message), token)
        cache[key] = result
        if result["status"] == "http_401":
            print("GitHub authentication failed (401). Check GITHUB_TOKEN.")
            break
        if n % 25 == 0 or result["status"] == "rate_limited":
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Processed {n:,}/{len(unique):,} unique lookups")
        if result["status"] == "rate_limited":
            print("GitHub API rate limit reached; stopping lookups. Rerun later to resume.")
            break
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    statuses = pd.Series([cache.get(key, {}).get("status", "not_checked") for key in resolved])
    print("Commit lookup statuses:", statuses.value_counts().to_dict())
    return pd.Series([cache.get(key, {}).get("sha") for key in resolved], dtype="string")


def load(
    input_path: Path = DEFAULT_INPUT,
    *,
    resolve_commits: bool = False,
    cache_path: Path = DEFAULT_CACHE,
    github_token: str | None = None,
) -> pd.DataFrame:
    _ensure_raw_csv(input_path)
    raw = pd.read_csv(input_path, dtype={"cwe_id": "string"}, low_memory=False)
    missing = sorted(REQUIRED_INPUT_COLUMNS - set(raw.columns))
    if missing:
        raise ValueError(f"Missing required CSV columns: {missing}")
    if resolve_commits and not {"committer_date", "commit_msg"}.issubset(raw.columns):
        raise ValueError("Commit enrichment requires committer_date and commit_msg")
    labels = (
        raw["is_vulnerable"]
        .astype("string")
        .str.strip()
        .str.lower()
        .map({"true": 1, "false": 0, "1": 1, "0": 0})
    )
    if labels.isna().any():
        raise ValueError("Unrecognized is_vulnerable values")

    if resolve_commits:
        commits = enrich_commits(raw, cache_path, github_token)
        raw["commit"] = commits
        raw.to_csv(input_path, index=False, encoding="utf-8")
        print(f"Updated raw CSV with resolved commits: {input_path}")
    elif "commit" in raw.columns:
        commits = raw["commit"].astype("string")
    else:
        commits = pd.Series(pd.NA, index=raw.index, dtype="string")

    standardized = pd.DataFrame(
        {
            "code": raw["vul_code"],
            "language": "python",
            "label": labels.astype("int8"),
            "cwe": raw["cwe_id"],
            "project": raw["repo_url"].map(project_from_repo_url),
            "commit": commits,
            "date": raw["committer_date"],  # commit date, not CVE publication date
            "cve": raw["cve_id"],
            "fixed_code": raw["patch"],
        }
    )
    result = conform(standardized, source=SOURCE)
    problems = validate(result)
    if problems:
        raise ValueError("Unified schema validation failed:\n- " + "\n- ".join(problems))
    if list(result.columns) != COLUMNS or len(result) != len(raw):
        raise AssertionError("Schema or row count mismatch")
    return result


def build_commit_cve_mapping(raw: pd.DataFrame) -> pd.DataFrame:
    """Build CVE links directly from the ORIGINAL Zenodo CSV columns.

    This intentionally does not depend on the conformed code table. Each source
    record contributes its original repository, commit (when available), date,
    and CVE association. Multiple CVE IDs in a cell are expanded to separate rows.
    Rows without a CVE are excluded; missing commits are retained because the
    original Zenodo records may not provide a resolvable SHA.
    """
    required = {"repo_url", "committer_date", "cve_id"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(
            f"Cannot build mapping from original Zenodo CSV; missing columns: {missing}"
        )

    commits = (
        raw["commit"].astype("string")
        if "commit" in raw.columns
        else pd.Series(pd.NA, index=raw.index, dtype="string")
    )
    links = pd.DataFrame(
        {
            "project": raw["repo_url"].map(project_from_repo_url),
            "commit": commits,
            "date": raw["committer_date"],
            "cve": raw["cve_id"],
        }
    )

    # The source CSV normally stores a single CVE per row; split cells that
    # contain multiple IDs as a defensive measure, then validate the IDs.
    links["cve"] = links["cve"].astype("string").str.upper().str.findall(r"CVE-\d{4}-\d{4,}")
    links = links.explode("cve").dropna(subset=["cve"])
    links["commit"] = links["commit"].astype("string").str.strip()
    links["date"] = links["date"].astype("string").str.strip()
    links["project"] = links["project"].astype("string").str.strip()
    return links[MAPPING_COLUMNS].drop_duplicates().reset_index(drop=True).astype("string")


def save_overwrite(df: pd.DataFrame, path: Path, *, mapping: bool = False) -> None:
    """Write a parquet file, replacing it if it already exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        print(f"Overwriting existing file: {path}")
    if mapping:
        df.to_parquet(path, engine="pyarrow", index=False)
    else:
        to_parquet(df, path)  # stable Arrow schema (list<string> for cwe / cve)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--mapping-output", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--resolve-commits", action="store_true")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    df = load(
        args.input,
        resolve_commits=args.resolve_commits,
        cache_path=args.cache,
        github_token=os.getenv("GITHUB_TOKEN"),
    )
    # Build the mapping from the source CSV itself, not from the standardized
    # code dataframe. If --resolve-commits was used, load() has already updated
    # the CSV's commit column before this read.
    raw_for_mapping = pd.read_csv(args.input, dtype={"cwe_id": "string"}, low_memory=False)
    mapping = build_commit_cve_mapping(raw_for_mapping)

    save_overwrite(df, args.output)
    save_overwrite(mapping, args.mapping_output, mapping=True)

    labels = df["label"].value_counts().to_dict()
    print(f"Saved: {args.output}")
    print(f"Saved: {args.mapping_output} ({len(mapping):,} project/commit-CVE links)")
    print(f"Rows: {len(df):,} | Columns: {list(df.columns)}")
    print(f"Labels: {labels}")
    if labels.get(0, 0) == 0:
        print("NOTE: no label-0 rows in this source (see D39 / patched negatives in splits.py)")
    print(f"Missing commits: {df['commit'].isna().sum():,}")
    print(f"Non-null dates: {df['date'].notna().sum():,}")
    print(f"Rows with at least one CVE: {int(df['cve'].map(len).gt(0).sum()):,}")
    print(f"Rows with at least one CWE: {int(df['cwe'].map(len).gt(0).sum()):,}")
    print("Deduplication: NOT performed")


if __name__ == "__main__":
    main()
