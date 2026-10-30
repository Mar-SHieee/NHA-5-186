from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shield_core.extraction import CachedGraphExtractor  # noqa: E402
from shield_core.extraction.cache import CacheKey, GraphCache  # noqa: E402
from shield_core.extraction.joern_extractor import JoernExtractor  # noqa: E402

SPLITS_DIR = ROOT / "data" / "interim" / "splits"
RUNS_DIR = ROOT / "data" / "interim" / "joern_runs"
CACHE_DIR = ROOT / "data" / "cache" / "graphs"


def sha256_text(value: str) -> str:
    """Keep the same sample-key hash convention as the previous runner."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resumable, non-batched Joern graph extraction with bounded concurrency."
    )
    parser.add_argument(
        "--split",
        choices=["train", "val", "test", "holdout"],
        required=True,
    )
    parser.add_argument("--language", choices=["python", "cpp"], default="python")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--start-row",
        type=int,
        default=0,
        help="Zero-based inclusive Parquet row position to start from.",
    )
    parser.add_argument(
        "--end-row",
        type=int,
        default=None,
        help="Zero-based exclusive Parquet row position to stop before (default: end of split).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of new samples to process in this run.",
    )
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument(
        "--progress",
        type=Path,
        default=None,
        help="Optional JSONL progress file. Existing JSONL records remain compatible.",
    )
    parser.add_argument(
        "--in-flight",
        type=int,
        default=None,
        help="Maximum submitted tasks at once (default: 2 * workers).",
    )
    return parser.parse_args()


def load_completed(progress_path: Path) -> set[str]:
    """Read successful sample keys from both old and new compatible JSONL records."""
    completed: set[str] = set()

    if not progress_path.exists():
        return completed

    with progress_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # Ignore a partial/corrupt final line from an interrupted run.
                continue

            sample_key = record.get("sample_key")
            if record.get("status") == "success" and isinstance(sample_key, str):
                completed.add(sample_key)

    return completed


def append_record(
    progress_path: Path,
    record: dict,
    lock: threading.Lock,
) -> None:
    serialized = json.dumps(record, ensure_ascii=False, default=str)
    with lock:
        with progress_path.open("a", encoding="utf-8") as handle:
            handle.write(serialized + "\n")
            handle.flush()


def iter_pending(
    input_path: Path,
    split: str,
    language: str,
    completed: set[str],
    limit: int | None,
    validation_cache: GraphCache,
    key_extractor: JoernExtractor,
    scan_stats: dict[str, int],
    start_row: int,
    end_row: int | None,
) -> Iterator[dict]:
    """
    Stream unique samples from a zero-based Parquet row range [start_row, end_row).
    Row positions refer to physical row order in the split file, before language
    filtering, invalid-code filtering, or duplicate removal.
    """
    parquet_file = pq.ParquetFile(input_path)
    seen_hashes: set[str] = set()
    scheduled = 0
    batch_size = 128
    parquet_row_offset = 0

    for batch in parquet_file.iter_batches(
        batch_size=batch_size,
        columns=["code", "language", "label"],
    ):
        batch_rows = batch.num_rows
        batch_start = parquet_row_offset
        batch_end = batch_start + batch_rows
        parquet_row_offset = batch_end

        # Skip batches outside the requested range.
        range_start = max(start_row, batch_start)
        range_end = min(end_row if end_row is not None else batch_end, batch_end)
        if range_start >= range_end:
            if end_row is not None and batch_start >= end_row:
                return
            continue

        frame = batch.slice(range_start - batch_start, range_end - range_start).to_pandas()
        frame["parquet_row"] = range(range_start, range_end)
        frame = frame.loc[frame["language"].eq(language)]

        for row in frame.itertuples(index=False):
            code = row.code
            parquet_row = row.parquet_row
            if not isinstance(code, str) or not code.strip():
                scan_stats["invalid_code"] += 1
                continue

            code_hash = sha256_text(code)
            if code_hash in seen_hashes:
                scan_stats["duplicate_code"] += 1
                continue

            seen_hashes.add(code_hash)
            index = int(parquet_row)
            scan_stats["unique_samples"] += 1
            sample_key = f"{split}:{language}:{code_hash}"

            if sample_key in completed:
                # Validate the on-disk graph rather than trusting the progress log alone.
                try:
                    key = CacheKey.for_code(code, language, key_extractor)
                    cached_graph = validation_cache.get(key)
                except Exception:
                    cached_graph = None

                if cached_graph is not None:
                    scan_stats["skipped_completed_cache_valid"] += 1
                    continue

                scan_stats["completed_but_cache_invalid"] += 1

            yield {
                "index": index,
                "sample_key": sample_key,
                "code_sha256": code_hash,
                "code": code,
            }
            scheduled += 1

            if limit is not None and scheduled >= limit:
                return


def main() -> None:
    args = parse_args()

    if args.workers < 1:
        raise SystemExit("--workers must be at least 1.")
    if args.timeout < 1 or args.retries < 0:
        raise SystemExit("--timeout must be positive and --retries non-negative.")
    if args.start_row < 0:
        raise SystemExit("--start-row must be >= 0.")
    if args.end_row is not None and args.end_row < 1:
        raise SystemExit("--end-row must be >= 1.")
    if args.end_row is not None and args.start_row >= args.end_row:
        raise SystemExit("--start-row must be smaller than --end-row.")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1.")
    if args.in_flight is not None and args.in_flight < 1:
        raise SystemExit("--in-flight must be at least 1.")

    input_path = SPLITS_DIR / f"{args.split}.parquet"
    if not input_path.is_file():
        raise SystemExit(f"Split file not found: {input_path}")

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    progress_path = args.progress
    if progress_path is None:
        end_label = args.end_row if args.end_row is not None else "end"
        progress_path = RUNS_DIR / (
            f"{args.split}_{args.language}_rows_{args.start_row}_{end_label}.jsonl"
        )
    elif not progress_path.is_absolute():
        progress_path = ROOT / progress_path
    progress_path.parent.mkdir(parents=True, exist_ok=True)

    max_in_flight = args.in_flight or max(args.workers, args.workers * 2)
    completed = load_completed(progress_path)

    print(f"Input:       {input_path}")
    print(f"Progress:    {progress_path}")
    print(f"Cache:       {CACHE_DIR}")
    print(f"Split:       {args.split}")
    print(f"Language:    {args.language}")
    print(f"Row range:   [{args.start_row}, {args.end_row if args.end_row is not None else 'end'})")
    print(f"Workers:     {args.workers}")
    print(f"In-flight:   {max_in_flight}")
    print(f"Timeout:     {args.timeout}s per attempt")
    print(f"Retries:     {args.retries}")
    print(f"Limit:       {args.limit if args.limit is not None else 'all remaining'}")
    print("Mode:        non-batched; streaming input; bounded task submission")
    print("Reading Parquet and validating previous successes...")

    # Used only to validate cached entries for records previously marked successful.
    validation_cache = GraphCache(CACHE_DIR)
    key_extractor = JoernExtractor(docker_image="shield-joern", timeout=args.timeout)

    scan_stats = {
        "unique_samples": 0,
        "invalid_code": 0,
        "duplicate_code": 0,
        "skipped_completed_cache_valid": 0,
        "completed_but_cache_invalid": 0,
    }
    pending_iter = iter_pending(
        input_path=input_path,
        split=args.split,
        language=args.language,
        completed=completed,
        limit=args.limit,
        validation_cache=validation_cache,
        key_extractor=key_extractor,
        scan_stats=scan_stats,
        start_row=args.start_row,
        end_row=args.end_row,
    )

    append_lock = threading.Lock()
    worker_caches: list[GraphCache] = []
    worker_caches_lock = threading.Lock()
    thread_local = threading.local()

    def get_worker_cache() -> GraphCache:
        cache = getattr(thread_local, "cache", None)
        if cache is None:
            cache = GraphCache(CACHE_DIR)
            thread_local.cache = cache
            with worker_caches_lock:
                worker_caches.append(cache)
        return cache

    def worker(item: dict) -> dict:
        started = time.monotonic()
        last_error: str | None = None
        attempts_used = 0
        cache = get_worker_cache()

        for attempt in range(args.retries + 1):
            attempts_used = attempt + 1
            timeout = args.timeout if attempt == 0 else max(args.timeout * 2, 180)

            try:
                extractor = CachedGraphExtractor(
                    JoernExtractor(
                        docker_image="shield-joern",
                        timeout=timeout,
                    ),
                    cache=cache,
                )
                graph = extractor.extract(item["code"], args.language)

                return {
                    "sample_key": item["sample_key"],
                    "code_sha256": item["code_sha256"],
                    "split": args.split,
                    "language": args.language,
                    "index": item["index"],
                    "status": "success",
                    "attempts": attempts_used,
                    "nodes": len(graph.nodes),
                    "edges": len(graph.edges),
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "finished_at": utc_now(),
                }
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"

        return {
            "sample_key": item["sample_key"],
            "code_sha256": item["code_sha256"],
            "split": args.split,
            "language": args.language,
            "index": item["index"],
            "status": "failed",
            "attempts": attempts_used,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "error": last_error,
            "finished_at": utc_now(),
        }

    succeeded = 0
    failed = 0
    completed_this_run = 0
    started = time.monotonic()
    futures: dict[Future, dict] = {}
    exhausted = False

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        while futures or not exhausted:
            while not exhausted and len(futures) < max_in_flight:
                try:
                    item = next(pending_iter)
                except StopIteration:
                    exhausted = True
                    break
                futures[pool.submit(worker, item)] = item

            if not futures:
                break

            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                futures.pop(future)
                record = future.result()
                append_record(progress_path, record, append_lock)
                completed_this_run += 1

                if record["status"] == "success":
                    succeeded += 1
                else:
                    failed += 1

                print(
                    f"[{completed_this_run}] {record['status'].upper()} "
                    f"index={record['index']} "
                    f"nodes={record.get('nodes', '-')} "
                    f"edges={record.get('edges', '-')} "
                    f"attempts={record['attempts']} "
                    f"time={record['elapsed_seconds']}s"
                )

    elapsed = time.monotonic() - started
    cache_hits = sum(int(cache.hits) for cache in worker_caches)
    cache_misses = sum(int(cache.misses) for cache in worker_caches)
    cache_total = cache_hits + cache_misses
    cache_hit_rate = cache_hits / cache_total if cache_total else 0.0

    print("\nRun summary")
    print(f"Processed this run:             {completed_this_run}")
    print(f"Success:                        {succeeded}")
    print(f"Failed:                         {failed}")
    print(f"Unique samples scanned:         {scan_stats['unique_samples']}")
    print(f"Duplicate code samples skipped: {scan_stats['duplicate_code']}")
    print(f"Invalid/empty code rows:         {scan_stats['invalid_code']}")
    print(f"Skipped (success + valid cache): {scan_stats['skipped_completed_cache_valid']}")
    print(f"Prior success, cache invalid:    {scan_stats['completed_but_cache_invalid']}")
    print(f"Cache hits during extraction:    {cache_hits}")
    print(f"Cache misses during extraction:  {cache_misses}")
    print(f"Extraction cache hit rate:       {cache_hit_rate:.2%}")
    print(f"Elapsed:                         {elapsed:.1f}s")
    print(f"Progress:                        {progress_path}")
    print("Successful samples are recorded for resume.")
    print("Failed samples remain eligible for retry on the next run.")


if __name__ == "__main__":
    main()
