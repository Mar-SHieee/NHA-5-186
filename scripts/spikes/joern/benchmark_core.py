"""Pure helpers for the Joern extraction benchmark (W2-P2-05).

No Docker, no network, no timing here: only arithmetic and list handling, so CI can test it.
"""

from __future__ import annotations

import csv
import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from shield_core.extraction.graph_extractor import code_sha256, normalize_code

T = TypeVar("T")

# group -> (registry language id, file extension). "c" and "cpp" share the registry language
# "cpp" but differ in extension, and the extension changes which Joern parser runs.
BENCH_GROUPS: dict[str, tuple[str, str]] = {
    "python": ("python", ".py"),
    "c": ("cpp", ".c"),
    "cpp": ("cpp", ".cpp"),
}


@dataclass(frozen=True)
class Sample:
    """One function to extract. `set_name` is "spike" (the 60 old samples) or "scale"."""

    sample_id: str
    group: str
    extension: str
    code: str
    set_name: str
    source: str  # dataset the row came from, e.g. "bigvul"
    row_index: int  # position of the row in that dataset's parquet file

    @property
    def n_chars(self) -> int:
        return len(normalize_code(self.code))

    @property
    def n_lines(self) -> int:
        return len(normalize_code(self.code).splitlines())

    @property
    def sha256(self) -> str:
        return code_sha256(self.code)


def split_batches(items: Sequence[T], size: int) -> list[list[T]]:
    """Cut `items` into consecutive batches of `size`; the last batch keeps the remainder."""
    if size < 1:
        raise ValueError(f"batch size must be >= 1, got {size}")
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def summarize(values: Sequence[float]) -> dict[str, float | int | None]:
    """n, mean, median, p95 (nearest-rank), min, max. An empty input means 'no data'."""
    if not values:
        return {"n": 0, "mean": None, "median": None, "p95": None, "min": None, "max": None}
    ordered = sorted(values)
    n = len(ordered)
    rank = -(-95 * n // 100)  # integer ceil(0.95 * n); avoids float rounding surprises
    return {
        "n": n,
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "p95": ordered[rank - 1],  # ranks are 1-indexed, lists are 0-indexed
        "min": ordered[0],
        "max": ordered[-1],
    }


def project_hours(n_rows: int, samples_per_second: float) -> float:
    """Hours needed to process `n_rows` at a measured throughput (rows per second)."""
    if samples_per_second <= 0:
        raise ValueError(f"throughput must be > 0, got {samples_per_second}")
    return n_rows / samples_per_second / 3600


def rows_per_night(samples_per_second: float, hours: float = 10.0) -> int:
    """Whole rows processed in `hours` at the measured throughput (truncated, so conservative)."""
    return int(samples_per_second * hours * 3600)


# ----------------------------------------------------------------------------- marker protocol

FAILURE_CLASSES = (
    "ok",
    "timeout",
    "oom",
    "joern_error",
    "no_export",
    "xml_error",
    "docker_error",
)

_DOCKER_DOWN = (
    "cannot connect to the docker daemon",
    "error during connect",
    "is the docker daemon running",
)


@dataclass
class Markers:
    """What the in-container script reported (see the @@ protocol in the benchmark plan)."""

    timings: dict[str, float] = field(default_factory=dict)  # "@@T <name> <seconds>"
    failures: dict[str, int] = field(default_factory=dict)  # "@@FAIL <name> <return code>"
    peak_bytes: int | None = None  # "@@PEAK <bytes>"; None when NA or missing


def parse_markers(stdout: str) -> Markers:
    """Extract @@ marker lines from container output. Everything else is noise and is ignored.

    A marker counts only when the line STARTS with '@@'. Malformed markers (wrong number of
    fields, non-numeric or non-finite values) are skipped instead of raising, because a
    container killed half-way can leave a truncated last line.
    """
    markers = Markers()
    for line in stdout.splitlines():  # splitlines also strips the \r of Windows line endings
        if not line.startswith("@@"):
            continue
        parts = line.split()
        tag = parts[0]
        try:
            if tag == "@@T" and len(parts) == 3:
                seconds = float(parts[2])
                if math.isfinite(seconds):
                    markers.timings[parts[1]] = seconds
            elif tag == "@@FAIL" and len(parts) == 3:
                markers.failures[parts[1]] = int(parts[2])
            elif tag == "@@PEAK" and len(parts) == 2:
                markers.peak_bytes = int(parts[1])
        except ValueError:
            continue  # "NA", "abc", "notanumber": skip the line, keep the rest
    return markers


def classify_failure(
    returncode: int | None, timed_out: bool, stderr: str, export_exists: bool
) -> str:
    """Give one run exactly one label from FAILURE_CLASSES.

    Precedence: timeout > docker_error > oom > joern_error > no_export > ok.
    (`xml_error` is never returned here: only the host-side XML parser can know about it.)
    """
    if timed_out:
        return "timeout"  # we killed it ourselves, so nothing else in the output can be trusted
    text = stderr.lower()
    if returncode is None or returncode == 125 or any(s in text for s in _DOCKER_DOWN):
        return "docker_error"
    if returncode == 137 or "outofmemoryerror" in text:
        return "oom"
    if returncode != 0:
        return "joern_error"
    return "ok" if export_exists else "no_export"


# ----------------------------------------------------------------------------- results files

RESULT_COLUMNS = [
    "run_id",
    "timestamp_utc",
    "experiment",
    "variant",
    "group",
    "extension",
    "set_name",
    "n_samples",
    "batch_size",
    "workers",
    "xmx",
    "rep",
    "wall_seconds",
    "seconds_per_sample",
    "samples_per_second",
    "ok_count",
    "fail_count",
    "fail_reasons_json",
    "peak_mib",
    "peak_method",
    "parse_seconds",
    "export_seconds",
    "xml_parse_seconds",
    "notes",
]

SAMPLE_COLUMNS = [
    "run_id",
    "sample_id",
    "group",
    "n_chars",
    "n_lines",
    "seconds",
    "ok",
    "failure_class",
    "nodes",
    "edges",
]


def config_key(
    variant: Any, group: Any, set_name: Any, workers: Any, batch_size: Any, xmx: Any, rep: Any
) -> tuple[str, ...]:
    """Identity of one configuration. Every part becomes a string, because a value read back
    from a CSV is always text: the int 1 written today must equal the "1" read tomorrow."""
    return tuple(str(p) for p in (variant, group, set_name, workers, batch_size, xmx, rep))


def append_row(path: str | Path, columns: Sequence[str], row: Mapping[str, Any]) -> None:
    """Append one row; create the file (and its folder) with a header if it is new.

    Raises ValueError for a column that is not in `columns`, or when an existing file has a
    different header (so a changed column list can never shift old data silently).
    None and missing columns are written as empty cells.
    """
    path = Path(path)
    unknown = set(row) - set(columns)
    if unknown:
        raise ValueError(f"unknown column(s): {sorted(unknown)}")

    write_header = True
    if path.exists() and path.stat().st_size > 0:
        with path.open(newline="", encoding="utf-8") as f:
            existing = next(csv.reader(f), [])
        if existing != list(columns):
            raise ValueError(f"{path} has header {existing}, expected {list(columns)}")
        write_header = False
    else:
        path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(columns)
        writer.writerow(["" if row.get(c) is None else row[c] for c in columns])


def read_rows(path: str | Path) -> list[dict[str, str]]:
    """All rows of a results file as dicts of strings. A missing file means 'no rows yet'."""
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def completed_keys(rows: Sequence[Mapping[str, str]]) -> set[tuple[str, ...]]:
    """Configurations already measured, for --resume.

    Warm-up runs (rep 0, or no usable rep) never count: they are redone. Failed runs DO count:
    a configuration that timed out was measured, and retrying it on every resume would loop.
    """
    done: set[tuple[str, ...]] = set()
    for r in rows:
        try:
            if int(r.get("rep", "")) < 1:
                continue
        except ValueError:
            continue
        done.add(
            config_key(
                r.get("variant"),
                r.get("group"),
                r.get("set_name"),
                r.get("workers"),
                r.get("batch_size"),
                r.get("xmx"),
                r.get("rep"),
            )
        )
    return done
