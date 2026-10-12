"""Load Zenodo data_Python.csv into SHIELD's unified 8-column schema.

From the repository root:
    python -m shield_core.datasets.python_loaders.zenodo_python_loader

Optional GitHub commit enrichment (uses GitHub API; may be rate limited):
    python -m shield_core.datasets.python_loaders.zenodo_python_loader --resolve-commits

Set GITHUB_TOKEN in your environment to increase the API rate limit.
No deduplication is performed.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

import pandas as pd

from shield_core.datasets.schema import COLUMNS, conform, validate

SOURCE = "zenodo_13870382_python"
DEFAULT_INPUT = Path("data/raw/zenodo_python/data_Python.csv")
DEFAULT_OUTPUT = Path("data/interim/zenodo_python.parquet")
DEFAULT_CACHE = Path("data/cache/zenodo_python_commit_cache.json")
REQUIRED_INPUT_COLUMNS = {"vul_code", "is_vulnerable", "repo_url", "cwe_id", "patch"}


def project_from_repo_url(value: object) -> object:
    if pd.isna(value) or not str(value).strip():
        return pd.NA
    parsed = urlparse(str(value).strip())
    if parsed.hostname not in {"github.com", "www.github.com"}:
        return pd.NA
    segments = [s for s in parsed.path.strip("/").split("/") if s]
    if len(segments) < 2:
        return pd.NA
    return f"{segments[0]}/{segments[1].removesuffix('.git')}"


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
        project = project_from_repo_url(repo)
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

        retryable_statuses = {
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

    print(f"Unique repo/date/message lookups: {len(unique):,}")

    for n, (key, (project, date, message)) in enumerate(unique.items(), 1):
        if key in cache and cache[key].get("status") not in retryable_statuses:
            continue
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
    commits = (
        enrich_commits(raw, cache_path, github_token)
        if resolve_commits
        else pd.Series(pd.NA, index=raw.index, dtype="string")
    )
    standardized = pd.DataFrame(
        {
            "code": raw["vul_code"],
            "language": "python",
            "label": labels.astype("int8"),
            "cwe": raw["cwe_id"],
            "project": raw["repo_url"].map(project_from_repo_url),
            "commit": commits,
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--resolve-commits", action="store_true")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    df = load(
        args.input,
        resolve_commits=args.resolve_commits,
        cache_path=args.cache,
        github_token=os.getenv("GITHUB_TOKEN"),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.output, engine="pyarrow", index=False)
    print(f"Saved: {args.output}")
    print(f"Rows: {len(df):,} | Columns: {list(df.columns)}")
    print(f"Labels: {df['label'].value_counts().to_dict()}")
    print(f"Missing commits: {df['commit'].isna().sum():,}")
    print("Deduplication: NOT performed")


if __name__ == "__main__":
    main()
