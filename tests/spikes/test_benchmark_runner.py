"""Joern extraction benchmark runner (W2-P2-05).

This file has two kinds of code, kept apart on purpose:
  * PURE builders (this section): they turn arguments into strings/lists, run nothing, and are
    unit-tested without Docker.
  * EXECUTORS (added in steps 3.3 to 3.7): they start Docker, time things and write results.

The in-container scripts talk to the host with a tiny line protocol, parsed by
`benchmark_core.parse_markers`:
    @@T <name> <seconds>     a timed phase, e.g. "@@T parse_3 1.482"
    @@FAIL <name> <rc>       a Joern command failed with this return code
    @@PEAK <bytes|NA>        peak memory of the container (cgroup counter), always the last line
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from scripts.spikes.joern.benchmark_core import (
    BENCH_GROUPS,
    RESULT_COLUMNS,
    SAMPLE_COLUMNS,
    Sample,
    append_row,
    classify_failure,
    completed_keys,
    config_key,
    parse_markers,
    read_rows,
    split_batches,
)
from scripts.spikes.joern.benchmark_samples import (
    draw_scale_samples,
    load_spike_samples,
    write_job_dir,
)
from shield_core.extraction.graph_extractor import ExtractionError
from shield_core.extraction.joern_extractor import (
    DEFAULT_DOCKER_IMAGE,
    DEFAULT_JOERN_VERSION,
    JoernExtractor,
    parse_graphml,
)
from shield_core.languages import registry
from shield_core.paths import BENCHMARK_DIR, REPO_ROOT

# Only plain file names may reach a shell script. This is a whitelist (what is allowed),
# not a blacklist (what is forbidden): anything unexpected is refused.
_SAFE_FILE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\-]*")
_SAFE_FRONTEND = re.compile(r"[a-z0-9]+")
_SAFE_CONTAINER = re.compile(r"shield-bench-[A-Za-z0-9_.\-]+")
_SAFE_XMX = re.compile(r"[0-9]+[gGmM]")

CONTAINER_PREFIX = "shield-bench-"  # cleanup helpers delete containers by this prefix

_PEAK_LINE = (
    'echo "@@PEAK $(cat /sys/fs/cgroup/memory.peak 2>/dev/null'
    " || cat /sys/fs/cgroup/memory/memory.max_usage_in_bytes 2>/dev/null"
    ' || echo NA)"'
)

# `dt A B` prints B - A with 3 decimals. awk is used because `bc` is not guaranteed in the image.
_PRELUDE = """\
now() { date +%s.%N; }
dt() { awk -v a="$1" -v b="$2" 'BEGIN{printf "%.3f", b-a}'; }
"""


def _check_files(files: Sequence[str]) -> None:
    if not files:
        raise ValueError("no files to run")
    for name in files:
        if not _SAFE_FILE.fullmatch(name):
            raise ValueError(f"unsafe file name: {name!r}")


def _joern_step(source: str, k: str, frontend: str) -> str:
    """parse then export for one input, with timings; a failure is recorded, never fatal.

    `source` is already quoted. `k` names the phase in the markers (parse_<k>, export_<k>).
    Joern's stdout is discarded (it is noisy and could never be a marker); stderr is kept so
    the host can still classify failures.
    """
    return f"""\
t0=$(now)
joern-parse {source} --language {frontend} -o cpg_{k}.bin >/dev/null; rc=$?
t1=$(now)
echo "@@T parse_{k} $(dt $t0 $t1)"
if [ $rc -ne 0 ]; then
  echo "@@FAIL {k} $rc"
else
  joern-export cpg_{k}.bin --repr all --format graphml --out export_{k} >/dev/null; rc=$?
  t2=$(now)
  echo "@@T export_{k} $(dt $t1 $t2)"
  if [ $rc -ne 0 ]; then echo "@@FAIL {k} $rc"; fi
fi
"""


def build_batch_script(variant: str, files: Sequence[str], frontend: str, batch_size: int) -> str:
    """Bash script for one container; its working directory is /workspace/job.

    variant "B": one `joern-parse` + one `joern-export` PER FILE (`batch_size` is ignored).
    variant "C": the files are cut into batches of `batch_size`; each batch is copied into its
                 own folder and gets ONE `joern-parse` and ONE `joern-export` for the folder.
    Variant A is not a script: it runs on the host through `JoernExtractor`.

    The script has no `set -e`, so a failing file cannot stop the others; the last line is
    always the @@PEAK marker.
    """
    if variant not in ("B", "C"):
        raise ValueError(f"variant must be 'B' or 'C' (A runs on the host), got {variant!r}")
    if batch_size < 1:
        raise ValueError(f"batch size must be >= 1, got {batch_size}")
    if not _SAFE_FRONTEND.fullmatch(frontend):
        raise ValueError(f"unsafe frontend name: {frontend!r}")
    _check_files(files)

    parts = [_PRELUDE]
    if variant == "B":
        for k, name in enumerate(files, start=1):
            parts.append(_joern_step(f"'{name}'", str(k), frontend))
    else:
        for j, batch in enumerate(split_batches(list(files), batch_size), start=1):
            quoted = " ".join(f"'{name}'" for name in batch)
            parts.append(f"mkdir batch_{j} && cp {quoted} batch_{j}/\n")
            parts.append(_joern_step(f"batch_{j}", str(j), frontend))
    parts.append(_PEAK_LINE + "\n")
    return "".join(parts)


def build_docker_command(image: str, job_dir: str, name: str, xmx: str, script: str) -> list[str]:
    """The `docker run` argument list (never a shell string, so nothing is re-parsed).

    `--mount` is used instead of `-v` because the Windows drive colon (C:\\...) confuses the
    `-v src:dst` syntax. `-e JAVA_OPTS=-Xmx<xmx>` caps Joern's JVM; note that Joern's separate
    frontend process may ignore it (plan risk R10), which is why peak memory is measured.
    """
    if not _SAFE_CONTAINER.fullmatch(name):
        raise ValueError(f"unsafe container name (must match shield-bench-<id>): {name!r}")
    if not _SAFE_XMX.fullmatch(xmx):
        raise ValueError(f"bad xmx {xmx!r}: use a number plus g or m, for example 4g")
    job_dir = str(job_dir)
    if "," in job_dir or '"' in job_dir:
        raise ValueError(f"job_dir must not contain ',' or '\"' (mount syntax): {job_dir!r}")
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--mount",
        f"type=bind,source={job_dir},target=/workspace/job",
        "-w",
        "/workspace/job",
        "-e",
        f"JAVA_OPTS=-Xmx{xmx}",
        image,
        "bash",
        "-c",
        script,
    ]


# ============================================================================ E0: environment


def parse_docker_info(text: str) -> dict[str, int | None]:
    """Parse the output of `docker info --format "{{.NCPU}} {{.MemTotal}}"`."""
    parts = text.split()
    try:
        if len(parts) != 2:
            raise ValueError
        return {"docker_cpus": int(parts[0]), "docker_mem_bytes": int(parts[1])}
    except ValueError:
        return {"docker_cpus": None, "docker_mem_bytes": None}


def is_inside_onedrive(path: object) -> bool:
    """True when the path has a OneDrive folder in it (plan risk R9: slow, noisy bind mounts)."""
    return "onedrive" in str(path).lower()


def _total_ram_bytes() -> int | None:
    """Physical RAM of the host, without needing psutil. None when it cannot be found."""
    try:
        if sys.platform == "win32":
            import ctypes

            class MemStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemStatus()
            status.dwLength = ctypes.sizeof(MemStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))  # type: ignore[attr-defined]
            return int(status.ullTotalPhys)
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (OSError, ValueError, AttributeError):
        return None


def _docker_text(run, cmd: list[str]) -> str | None:
    """Stdout of a docker command, or None if docker is missing, down or the command fails."""
    try:
        done = run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def capture_environment(image: str, notes: str = "", run=subprocess.run) -> dict:
    """E0: everything about the machine that could explain a timing, as one dict.

    Never raises because of Docker: a benchmark run on a machine without a working Docker
    still gets an environment record, with None where the value could not be read.
    `notes` is for what only the human knows (power mode, plugged in, apps closed).
    """
    info = _docker_text(run, ["docker", "info", "--format", "{{.NCPU}} {{.MemTotal}}"])
    image_id = _docker_text(run, ["docker", "image", "inspect", "--format", "{{.Id}}", image])
    return {
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "os": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "ram_bytes": _total_ram_bytes(),
        **parse_docker_info(info or ""),
        "image": image,
        "image_id": image_id,
        "joern_version": DEFAULT_JOERN_VERSION,  # what the image is built to contain
        "repo_inside_onedrive": is_inside_onedrive(REPO_ROOT),
        "notes": notes,
    }


# ============================================================================ executors


# ============================================================================ executors

_EXEC_FAIL_RE = re.compile(r"^.+? failed \((-?\d+)\): (.*)\Z", re.DOTALL)


@dataclass
class SampleResult:
    sample_id: str
    group: str
    n_chars: int
    n_lines: int
    seconds: float | None  # per-sample time (in-container parse+export for B; host extract for A)
    ok: bool
    failure_class: str
    nodes: int | None = None
    edges: int | None = None


@dataclass
class RunOutcome:
    """Everything measured in one run."""

    wall_seconds: float
    results: list[SampleResult] = field(default_factory=list)
    peak_mib: float | None = None
    peak_method: str = "NA"
    parse_seconds: float | None = None  # None when black-box (variant A)
    export_seconds: float | None = None
    xml_parse_seconds: float | None = None
    stderr_tail: str = ""
    # variant C only: batch number (1-based) -> (nodes, edges) of that batch's combined graph.
    # Per-sample counts are impossible until Phase 7 solves attribution.
    batch_graphs: dict[int, tuple[int, int]] = field(default_factory=dict)


def _classify_extraction_error(exc: ExtractionError) -> tuple[str, str]:
    """Map an ExtractionError from JoernExtractor back to FAILURE_CLASSES and a stderr tail."""
    msg = str(exc)
    cause = exc.__cause__
    if isinstance(cause, subprocess.TimeoutExpired):
        return "timeout", ""
    if isinstance(cause, OSError):
        return "docker_error", msg
    if isinstance(cause, (ET.ParseError, ValueError)) or msg.startswith(
        "cannot parse Joern GraphML"
    ):
        return "xml_error", msg
    if msg == "joern-export produced no GraphML file":
        return "no_export", msg
    match = _EXEC_FAIL_RE.match(msg)
    if match:
        rc, stderr = int(match.group(1)), match.group(2)
        return classify_failure(rc, False, stderr, False), stderr
    return classify_failure(1, False, msg, False), msg


def run_variant_a(
    samples: Sequence[Sample],
    *,
    image: str,
    timeout: int,
    workers: int = 1,
    run=subprocess.run,
) -> RunOutcome:
    """Variant A: the production path (one JoernExtractor.extract call per sample, no cache).

    With `workers` > 1 a thread pool runs that many extractions at once (each starts its own
    container). `wall_seconds` is the wall-clock of the whole loop, not the sum of the samples.
    """
    if not samples:
        raise ValueError("no samples to run")
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers}")
    groups = {s.group for s in samples}
    if len(groups) != 1:
        raise ValueError(f"one group per run, got {sorted(groups)}")
    lang, _ = BENCH_GROUPS[samples[0].group]
    extractor = JoernExtractor(docker_image=image, timeout=timeout, runner=run)

    def one(s: Sample) -> tuple[SampleResult, str]:
        t0 = time.perf_counter()
        try:
            graph = extractor.extract(s.code, lang, extension=s.extension)
            dt = time.perf_counter() - t0
            ok = SampleResult(
                s.sample_id, s.group, s.n_chars, s.n_lines, dt, True, "ok",
                len(graph.nodes), len(graph.edges),
            )  # fmt: skip
            return ok, ""
        except ExtractionError as exc:
            dt = time.perf_counter() - t0
            failure, err = _classify_extraction_error(exc)
            seconds = None if failure == "timeout" else dt
            failed = SampleResult(
                s.sample_id, s.group, s.n_chars, s.n_lines, seconds, False, failure
            )
            return failed, err

    t_run = time.perf_counter()
    if workers == 1:
        pairs = [one(s) for s in samples]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pairs = list(pool.map(one, samples))  # map keeps the input order
    wall = time.perf_counter() - t_run
    errors = [err for _, err in pairs if err]
    return RunOutcome(
        wall_seconds=wall,
        results=[r for r, _ in pairs],
        stderr_tail=errors[-1][-500:] if errors else "",
    )


def pick_decompose_samples(samples: Sequence[Sample], n_each: int = 5) -> list[tuple[str, Sample]]:
    """E2 inputs: per group the `n_each` shortest and `n_each` longest functions (by lines).

    Returns (size_class, sample) pairs, groups in python, c, cpp order, small before large.
    A sample is never used twice, even when a group has fewer than 2 * n_each samples.
    """
    picked: list[tuple[str, Sample]] = []
    for group in BENCH_GROUPS:
        mine = sorted(
            (s for s in samples if s.group == group), key=lambda s: (s.n_lines, s.sample_id)
        )
        small = mine[:n_each]
        large = [s for s in mine[::-1] if s not in small][:n_each][::-1]
        picked += [("small", s) for s in small] + [("large", s) for s in large]
    return picked


def _find_export(job_dir: Path, k: int) -> Path | None:
    folder = job_dir / f"export_{k}"
    if (folder / "export.xml").exists():
        return folder / "export.xml"
    found = sorted(folder.glob("*.xml")) if folder.exists() else []
    return found[0] if found else None


def _force_remove(run, name: str) -> None:
    """`docker rm -f` that never raises (it runs in `finally`, where raising hides the cause)."""
    try:
        run(["docker", "rm", "-f", name], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass


def run_variant_b(
    samples: Sequence[Sample],
    *,
    image: str,
    xmx: str,
    timeout: int,
    work_dir: Path,
    run_id: str,
    keep: bool = False,
    run=subprocess.run,
) -> RunOutcome:
    """Variant B: ONE container, the samples one after the other (parse + export each).

    Compared with variant A (one container per sample) it removes the Docker start-up per
    sample, and it reports parse and export time separately. All samples must be from one group
    because the container is started with one Joern frontend.
    """
    if not samples:
        raise ValueError("no samples to run")
    groups = {s.group for s in samples}
    if len(groups) != 1:
        raise ValueError(f"one group per container, got {sorted(groups)}")
    group = samples[0].group
    frontend = registry.require_enabled(BENCH_GROUPS[group][0]).joern_frontend.lower()

    job_dir = Path(work_dir) / run_id
    paths = write_job_dir(job_dir, samples)
    os.chmod(job_dir, 0o777)  # the container user is not root; it must be able to write here
    script = build_batch_script("B", [p.name for p in paths], frontend, 1)
    name = f"{CONTAINER_PREFIX}{run_id}"
    cmd = build_docker_command(image, str(job_dir), name, xmx, script)
    limit = timeout + 10 * len(samples)

    timed_out, launch_failed, proc = False, False, None
    t0 = time.perf_counter()
    try:
        proc = run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=limit
        )
    except subprocess.TimeoutExpired:
        timed_out = True
    except OSError:  # the `docker` program itself cannot be started
        launch_failed = True
    finally:
        wall = time.perf_counter() - t0
        _force_remove(run, name)  # also kills a container that outlived a timeout

    stdout = proc.stdout if proc else ""
    stderr = proc.stderr if proc else ""
    markers = parse_markers(stdout)
    container_failed = proc is not None and proc.returncode != 0

    outcome = RunOutcome(wall_seconds=wall, stderr_tail=(stderr or "")[-500:])
    if markers.peak_bytes is not None:
        outcome.peak_mib = markers.peak_bytes / (1024 * 1024)
        outcome.peak_method = "cgroup"  # memory.peak (v2) or max_usage_in_bytes (v1)

    parse_sum = export_sum = xml_sum = 0.0
    try:
        for k, s in enumerate(samples, start=1):
            parse_t = markers.timings.get(f"parse_{k}")
            export_t = markers.timings.get(f"export_{k}")
            parse_sum += parse_t or 0.0
            export_sum += export_t or 0.0
            seconds = None if timed_out else (parse_t or 0.0) + (export_t or 0.0)
            nodes = edges = None

            if timed_out:
                failure = "timeout"
            elif launch_failed:
                failure = "docker_error"
            elif container_failed and not markers.timings and not markers.failures:
                failure = classify_failure(proc.returncode, False, stderr, False)
            elif str(k) in markers.failures:
                failure = classify_failure(markers.failures[str(k)], False, stderr, False)
            else:
                export = _find_export(job_dir, k)
                if export is None:
                    failure = "no_export"
                else:
                    t1 = time.perf_counter()
                    try:
                        parsed_nodes, parsed_edges = parse_graphml(export)
                        nodes, edges, failure = (
                            len(parsed_nodes),
                            len(parsed_nodes and parsed_edges),
                            "ok",
                        )
                    except (ET.ParseError, ValueError):
                        failure = "xml_error"
                    xml_sum += time.perf_counter() - t1

            outcome.results.append(
                SampleResult(
                    s.sample_id,
                    s.group,
                    s.n_chars,
                    s.n_lines,
                    seconds,
                    failure == "ok",
                    failure,
                    nodes,
                    edges,
                )  # fmt: skip
            )
    finally:
        if not keep:
            shutil.rmtree(job_dir, ignore_errors=True)
    outcome.parse_seconds = parse_sum
    outcome.export_seconds = export_sum
    outcome.xml_parse_seconds = xml_sum
    return outcome


def run_variant_c(
    samples: Sequence[Sample],
    *,
    image: str,
    xmx: str,
    timeout: int,
    batch_size: int,
    work_dir: Path,
    run_id: str,
    keep: bool = False,
    run=subprocess.run,
) -> RunOutcome:
    """Variant C: ONE container; the samples are cut into batches of `batch_size`, and each
    batch gets ONE `joern-parse` and ONE `joern-export` for its whole folder.

    The JVM start-up is paid once per batch instead of once per sample. Cost of that saving:
    a batch yields ONE combined graph, so the graph cannot be split back into per-sample graphs
    here (Phase 7 investigates that). Consequences for the numbers:
      * `SampleResult.seconds` is the batch's parse+export time divided equally among its
        samples (an apportioned figure, not a measurement per sample);
      * `nodes`/`edges` per sample are None; the batch totals are in `batch_graphs`;
      * a failing batch marks EVERY sample of that batch as failed (one export = all or nothing).
    """
    if not samples:
        raise ValueError("no samples to run")
    if batch_size < 1:
        raise ValueError(f"batch size must be >= 1, got {batch_size}")
    groups = {s.group for s in samples}
    if len(groups) != 1:
        raise ValueError(f"one group per container, got {sorted(groups)}")
    group = samples[0].group
    frontend = registry.require_enabled(BENCH_GROUPS[group][0]).joern_frontend.lower()
    batches = split_batches(list(samples), batch_size)

    job_dir = Path(work_dir) / run_id
    paths = write_job_dir(job_dir, samples)
    os.chmod(job_dir, 0o777)  # the container user is not root; it must be able to write here
    script = build_batch_script("C", [p.name for p in paths], frontend, batch_size)
    name = f"{CONTAINER_PREFIX}{run_id}"
    cmd = build_docker_command(image, str(job_dir), name, xmx, script)
    limit = timeout + 10 * len(samples)

    timed_out, launch_failed, proc = False, False, None
    t0 = time.perf_counter()
    try:
        proc = run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=limit
        )
    except subprocess.TimeoutExpired:
        timed_out = True
    except OSError:  # the `docker` program itself cannot be started
        launch_failed = True
    finally:
        wall = time.perf_counter() - t0
        _force_remove(run, name)  # also kills a container that outlived a timeout

    stdout = proc.stdout if proc else ""
    stderr = proc.stderr if proc else ""
    markers = parse_markers(stdout)
    container_failed = proc is not None and proc.returncode != 0

    outcome = RunOutcome(wall_seconds=wall, stderr_tail=(stderr or "")[-500:])
    if markers.peak_bytes is not None:
        outcome.peak_mib = markers.peak_bytes / (1024 * 1024)
        outcome.peak_method = "cgroup"

    parse_sum = export_sum = xml_sum = 0.0
    try:
        for j, batch in enumerate(batches, start=1):
            parse_t = markers.timings.get(f"parse_{j}")
            export_t = markers.timings.get(f"export_{j}")
            parse_sum += parse_t or 0.0
            export_sum += export_t or 0.0
            batch_seconds = (parse_t or 0.0) + (export_t or 0.0)

            if timed_out:
                failure = "timeout"
            elif launch_failed:
                failure = "docker_error"
            elif container_failed and not markers.timings and not markers.failures:
                failure = classify_failure(proc.returncode, False, stderr, False)
            elif str(j) in markers.failures:
                failure = classify_failure(markers.failures[str(j)], False, stderr, False)
            else:
                export = _find_export(job_dir, j)
                if export is None:
                    failure = "no_export"
                else:
                    t1 = time.perf_counter()
                    try:
                        parsed_nodes, parsed_edges = parse_graphml(export)
                        outcome.batch_graphs[j] = (len(parsed_nodes), len(parsed_edges))
                        failure = "ok"
                    except (ET.ParseError, ValueError):
                        failure = "xml_error"
                    xml_sum += time.perf_counter() - t1

            seconds = None if timed_out else batch_seconds / len(batch)
            for s in batch:
                outcome.results.append(
                    SampleResult(
                        s.sample_id,
                        s.group,
                        s.n_chars,
                        s.n_lines,
                        seconds,
                        failure == "ok",
                        failure,
                    )
                )
    finally:
        if not keep:
            shutil.rmtree(job_dir, ignore_errors=True)
    outcome.parse_seconds = parse_sum
    outcome.export_seconds = export_sum
    outcome.xml_parse_seconds = xml_sum
    return outcome


def _run_container_variant(variant: str, batch_size: int, samples: Sequence[Sample], **kw):
    if variant == "B":
        return run_variant_b(samples, **kw)
    if variant == "C":
        return run_variant_c(samples, batch_size=batch_size, **kw)
    raise ValueError(f"variant must be 'B' or 'C' here, got {variant!r}")


def merge_outcomes(outcomes: Sequence[RunOutcome], order: Sequence[str]) -> RunOutcome:
    """Combine the outcomes of containers that ran at the same time into one run.

    * wall = the SLOWEST container (they were started together, the run ends with the last);
    * peak = the highest single-container peak (a per-worker figure; workers x peak is what
      Docker's memory limit has to hold);
    * phase times and XML time are summed (total work, not wall);
    * results are put back into the original sample `order`.
    """
    position = {sid: k for k, sid in enumerate(order)}
    results = sorted((r for o in outcomes for r in o.results), key=lambda r: position[r.sample_id])
    peaks = [o.peak_mib for o in outcomes if o.peak_mib is not None]

    def total(name: str) -> float | None:
        values = [getattr(o, name) for o in outcomes if getattr(o, name) is not None]
        return sum(values) if values else None

    merged = RunOutcome(
        wall_seconds=max(o.wall_seconds for o in outcomes),
        results=results,
        peak_mib=max(peaks) if peaks else None,
        peak_method="cgroup" if peaks else "NA",
        parse_seconds=total("parse_seconds"),
        export_seconds=total("export_seconds"),
        xml_parse_seconds=total("xml_parse_seconds"),
        stderr_tail=next((o.stderr_tail for o in outcomes if o.stderr_tail), ""),
    )
    for o in outcomes:  # renumber so batches of different containers do not collide
        for graph in o.batch_graphs.values():
            merged.batch_graphs[len(merged.batch_graphs) + 1] = graph
    return merged


def run_sharded(
    variant: str,
    samples: Sequence[Sample],
    *,
    workers: int,
    batch_size: int,
    image: str,
    xmx: str,
    timeout: int,
    work_dir: Path,
    run_id: str,
    keep: bool = False,
    run=subprocess.run,
) -> RunOutcome:
    """Variant B or C with `workers` containers at once.

    The samples are dealt round-robin (sample i goes to shard i % workers) so a heavy sample
    does not make one shard much longer than the rest. Each shard is one container; with C a
    shard is cut into batches of at most `batch_size`, so with many workers batches can be
    smaller than `batch_size`. Never more containers than samples.
    """
    if not samples:
        raise ValueError("no samples to run")
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers}")
    shards = [list(samples[k::workers]) for k in range(workers)]
    shards = [sh for sh in shards if sh]
    common = {"image": image, "xmx": xmx, "timeout": timeout, "work_dir": work_dir}
    common |= {"keep": keep, "run": run}
    if len(shards) == 1:
        return _run_container_variant(variant, batch_size, shards[0], run_id=run_id, **common)

    def one(item: tuple[int, list[Sample]]) -> RunOutcome:
        k, shard = item
        return _run_container_variant(variant, batch_size, shard, run_id=f"{run_id}-s{k}", **common)

    with ThreadPoolExecutor(max_workers=len(shards)) as pool:
        outcomes = list(pool.map(one, enumerate(shards, start=1)))
    return merge_outcomes(outcomes, [s.sample_id for s in samples])


def outcome_to_result_row(
    outcome: RunOutcome,
    *,
    run_id: str,
    experiment: str,
    variant: str,
    group: str,
    extension: str,
    set_name: str,
    batch_size: int,
    workers: int,
    xmx: str,
    rep: int,
    notes: str = "",
) -> dict:
    """One results.csv row (keys are a subset of RESULT_COLUMNS)."""
    n = len(outcome.results)
    ok = sum(1 for r in outcome.results if r.ok)
    reasons = Counter(r.failure_class for r in outcome.results if not r.ok)
    wall = outcome.wall_seconds
    return {
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "experiment": experiment,
        "variant": variant,
        "group": group,
        "extension": extension,
        "set_name": set_name,
        "n_samples": n,
        "batch_size": batch_size,
        "workers": workers,
        "xmx": xmx,
        "rep": rep,
        "wall_seconds": round(wall, 3),
        "seconds_per_sample": round(wall / n, 3) if n else None,
        "samples_per_second": round(n / wall, 4) if n and wall > 0 else None,
        "ok_count": ok,
        "fail_count": n - ok,
        "fail_reasons_json": json.dumps(dict(reasons), sort_keys=True),
        "peak_mib": round(outcome.peak_mib, 1) if outcome.peak_mib is not None else None,
        "peak_method": outcome.peak_method,
        "parse_seconds": (
            round(outcome.parse_seconds, 3) if outcome.parse_seconds is not None else None
        ),
        "export_seconds": (
            round(outcome.export_seconds, 3) if outcome.export_seconds is not None else None
        ),
        "xml_parse_seconds": (
            round(outcome.xml_parse_seconds, 3) if outcome.xml_parse_seconds is not None else None
        ),
        "notes": notes,
    }


def outcome_to_sample_rows(
    outcome: RunOutcome, *, run_id: str, samples: Sequence[Sample]
) -> list[dict]:
    """One samples.csv row per sample of the run (keys are a subset of SAMPLE_COLUMNS)."""
    return [
        {
            "run_id": run_id,
            "sample_id": r.sample_id,
            "group": r.group,
            "n_chars": r.n_chars,
            "n_lines": r.n_lines,
            "seconds": round(r.seconds, 3) if r.seconds is not None else None,
            "ok": int(r.ok),
            "failure_class": r.failure_class,
            "nodes": r.nodes,
            "edges": r.edges,
        }
        for r in outcome.results
    ]


def measure_docker_floor(image: str, reps: int = 5, run=subprocess.run) -> list[float]:
    """Seconds for `docker run --rm <image> true`: the cost of starting a container alone."""
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        run(["docker", "run", "--rm", image, "true"], capture_output=True, text=True, timeout=120)
        times.append(time.perf_counter() - t0)
    return times


def record_run(out_dir: Path, outcome: RunOutcome, samples: Sequence[Sample], **row_args) -> dict:
    """Append the run to results.csv and its samples to samples.csv, immediately."""
    row = outcome_to_result_row(outcome, **row_args)
    append_row(Path(out_dir) / "results.csv", RESULT_COLUMNS, row)
    for srow in outcome_to_sample_rows(outcome, run_id=row_args["run_id"], samples=samples):
        append_row(Path(out_dir) / "samples.csv", SAMPLE_COLUMNS, srow)
    return row


def _limit_per_group(samples: Sequence[Sample], limit: int | None) -> list[Sample]:
    """Keep at most `limit` samples per group while preserving file order."""
    if limit is None:
        return list(samples)
    counts: Counter[str] = Counter()
    kept: list[Sample] = []
    for s in samples:
        if counts[s.group] < limit:
            kept.append(s)
            counts[s.group] += 1
    return kept


def run_decompose(
    samples: Sequence[Sample],
    *,
    image: str,
    xmx: str,
    timeout: int,
    work_dir: Path,
    out_dir: Path,
    reps: int = 1,
    seed: int = 42,
    warmup: bool = True,
    keep: bool = False,
    floor_reps: int = 5,
    run=subprocess.run,
    echo=print,
) -> None:
    """E2: where does the time of ONE sample go? Docker start-up vs parse vs export vs XML.

    Runs variant B with one sample per container on the shortest and longest functions of each
    group. Order is shuffled with a fixed seed (so slow drift of the machine does not always hit
    the same group), and one throw-away warm-up run comes first (rep 0, never used in statistics).
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    floor_id = f"{stamp}-floor"
    for rep, t in enumerate(measure_docker_floor(image, floor_reps, run), start=1):
        floor = RunOutcome(wall_seconds=t)
        append_row(
            Path(out_dir) / "results.csv",
            RESULT_COLUMNS,
            {
                "run_id": f"{floor_id}-r{rep}", "timestamp_utc": stamp, "experiment": "E2",
                "variant": "floor", "n_samples": 0, "workers": 1, "xmx": xmx, "rep": rep,
                "wall_seconds": round(floor.wall_seconds, 3),
                "notes": "docker run --rm <image> true",
            },
        )  # fmt: skip
        echo(f"[floor] rep {rep}: {t:.3f} s")

    plan = pick_decompose_samples(samples)
    random.Random(seed).shuffle(plan)

    jobs: list[tuple[int, str, Sample]] = []
    if warmup and plan:
        jobs.append((0, "warmup", plan[0][1]))
    jobs += [(rep, cls, s) for rep in range(1, reps + 1) for cls, s in plan]

    for rep, cls, s in jobs:
        run_id = f"{stamp}-B-w1-b1-{s.sample_id}-r{rep}"
        outcome = run_variant_b(
            [s],
            image=image,
            xmx=xmx,
            timeout=timeout,
            work_dir=work_dir,
            run_id=run_id,
            keep=keep,
            run=run,
        )
        row = record_run(
            out_dir, outcome, [s], run_id=run_id, experiment="E2", variant="B", group=s.group,
            extension=s.extension, set_name=s.set_name, batch_size=1, workers=1, xmx=xmx,
            rep=rep, notes=cls,
        )  # fmt: skip
        r = outcome.results[0]
        echo(
            f"[{cls:<6}] {s.sample_id:<18} lines={s.n_lines:<4} rep={rep} {r.failure_class:<11} "
            f"wall={row['wall_seconds']}s parse={row['parse_seconds']}s "
            f"export={row['export_seconds']}s xml={row['xml_parse_seconds']}s "
            f"peak={row['peak_mib']} MiB nodes={r.nodes} edges={r.edges}"
        )


def _run_config(
    variant: str,
    batch_size: int,
    workers: int,
    group_samples: Sequence[Sample],
    *,
    image: str,
    xmx: str,
    timeout: int,
    work_dir: Path,
    run_id: str,
    keep: bool = False,
    run=subprocess.run,
) -> RunOutcome:
    """One configuration (variant, batch size, workers) on the samples of ONE group."""
    if variant == "A":
        return run_variant_a(group_samples, image=image, timeout=timeout, workers=workers, run=run)
    if variant not in ("B", "C"):
        raise ValueError(f"unsupported variant: {variant!r}")
    return run_sharded(
        variant,
        group_samples,
        workers=workers,
        batch_size=batch_size,
        image=image,
        xmx=xmx,
        timeout=timeout,
        work_dir=work_dir,
        run_id=run_id,
        keep=keep,
        run=run,
    )


def _run_grid(
    experiment: str,
    samples: Sequence[Sample],
    configs: Sequence[tuple[str, int, int]],
    *,
    image: str,
    xmx: str,
    timeout: int,
    work_dir: Path,
    out_dir: Path,
    reps: int,
    seed: int = 42,
    warmup: bool = True,
    keep: bool = False,
    resume: bool = False,
    run=subprocess.run,
    echo=print,
) -> None:
    """Run every (variant, batch size, workers) config on every group, `reps` times.

    Jobs are shuffled with a fixed seed. One throw-away warm-up per variant comes first (rep 0).
    With `resume`, jobs whose config_key is already in results.csv (rep >= 1) are skipped.
    """
    by_group = {g: [s for s in samples if s.group == g] for g in BENCH_GROUPS}
    active_groups = [g for g, grp in by_group.items() if grp]
    if not active_groups or not configs:
        return

    results_path = Path(out_dir) / "results.csv"
    done = completed_keys(read_rows(results_path)) if resume and results_path.exists() else set()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    jobs = [
        (rep, v, b, w, g)
        for rep in range(1, reps + 1)
        for v, b, w in configs
        for g in active_groups
    ]
    jobs.sort(key=lambda j: (j[0], j[1], j[2], j[3], j[4]))  # stable base order before shuffling
    random.Random(seed).shuffle(jobs)
    pending = []
    for rep, v, b, w, g in jobs:
        if config_key(v, g, by_group[g][0].set_name, w, b, xmx, rep) in done:
            echo(f"[skip] {v} b={b} w={w} {g} rep={rep} (already in results.csv)")
        else:
            pending.append((rep, v, b, w, g))
    if not pending:
        return

    def execute(
        rep: int, v: str, b: int, w: int, group_samples: Sequence[Sample], tag: str, notes=""
    ):
        first = group_samples[0]
        run_id = f"{stamp}-{v}-w{w}-b{b}-{tag}-r{rep}"
        outcome = _run_config(
            v, b, w, group_samples,
            image=image, xmx=xmx, timeout=timeout, work_dir=work_dir,
            run_id=run_id, keep=keep, run=run,
        )  # fmt: skip
        row = record_run(
            out_dir, outcome, group_samples, run_id=run_id, experiment=experiment, variant=v,
            group=first.group, extension=first.extension, set_name=first.set_name,
            batch_size=b, workers=w, xmx=xmx, rep=rep, notes=notes,
        )  # fmt: skip
        return outcome, row

    if warmup:
        first_sample = by_group[active_groups[0]][0]
        for v in dict.fromkeys(v for v, _, _ in configs):
            _, row = execute(0, v, 1, 1, [first_sample], first_sample.group, notes="warmup")
            echo(f"[warmup] {v} {first_sample.sample_id} wall={row['wall_seconds']}s")

    for rep, v, b, w, g in pending:
        outcome, row = execute(rep, v, b, w, by_group[g], g)
        if outcome.batch_graphs:  # variant C: one combined graph per batch
            detail = ", ".join(
                f"batch{j}:{n}n/{e}e" for j, (n, e) in sorted(outcome.batch_graphs.items())[:3]
            )
            failed = [r for r in outcome.results if not r.ok]
            if failed:
                detail += f" | {len(failed)} failed: {failed[0].failure_class}"
        else:
            detail = ", ".join(
                f"{r.sample_id}:{r.failure_class}({r.nodes}n/{r.edges}e)"
                for r in outcome.results[:3]
            )
        echo(
            f"[{v} b={b:<2} w={w}] {g:<6} n={row['n_samples']:<3} rep={rep} "
            f"ok={row['ok_count']}/{row['n_samples']} wall={row['wall_seconds']}s "
            f"s/sample={row['seconds_per_sample']}s peak={row['peak_mib']} MiB | {detail}"
        )


def run_variants(
    samples: Sequence[Sample],
    *,
    reps: int = 3,
    variant_filter: str | None = None,
    batch_sizes: Sequence[int] = (10, 20, 50),
    **kw,
) -> None:
    """E1 + E3: single-worker comparison across groups (A, B and C for each batch size)."""
    configs = [("A", 1, 1), ("B", 1, 1)] + [("C", n, 1) for n in batch_sizes]
    if variant_filter is not None:
        configs = [c for c in configs if c[0] == variant_filter]
    _run_grid("E3", samples, configs, reps=reps, **kw)


def pick_best_config(
    out_dir: Path, default: tuple[str, int] = ("C", 20)
) -> tuple[tuple[str, int], bool]:
    """The fastest container variant of E3: (variant, batch size) and whether data decided it.

    Looks at error-free E3 rows of B and C (rep >= 1) and compares the median of
    (wall + host XML parse) / samples: variant B's wall does not include the XML parse that
    variant A and the production path do, so it is added for a fair comparison.
    """
    path = Path(out_dir) / "results.csv"
    values: dict[tuple[str, int], list[float]] = {}
    for r in read_rows(path) if path.exists() else []:
        try:
            if r["experiment"] != "E3" or r["variant"] not in ("B", "C") or int(r["rep"]) < 1:
                continue
            if int(r["fail_count"]) != 0 or int(r["n_samples"]) < 1:
                continue
            per_sample = (float(r["wall_seconds"]) + float(r["xml_parse_seconds"] or 0)) / int(
                r["n_samples"]
            )
            values.setdefault((r["variant"], int(r["batch_size"])), []).append(per_sample)
        except (KeyError, ValueError):
            continue
    if not values:
        return default, False
    medians = {k: sorted(v)[len(v) // 2] for k, v in values.items()}
    return min(medians, key=medians.get), True


def run_workers(
    samples: Sequence[Sample],
    *,
    best: tuple[str, int],
    workers_list: Sequence[int] = (1, 2, 4),
    reps: int = 2,
    experiment: str = "E4",
    **kw,
) -> None:
    """E4 (E5 with experiment="E5"): variant A and the best container variant per worker count."""
    bv, bb = best
    configs = [("A", 1, w) for w in workers_list] + [(bv, bb, w) for w in workers_list]
    _run_grid(experiment, samples, configs, reps=reps, **kw)


# ----------------------------------------------------------------------------- dry run

# Rough per-sample seconds, from the hand runs of steps 3.4 to 3.6. Only used to size a dry run.
_EST_SECONDS_PER_SAMPLE = {"A": 9.0, "B": 8.0, "C": 3.5, "floor": 0.7, "env": 5.0}
_EST_PARALLEL_EFFICIENCY = 0.7  # assumed, NOT measured: this is what E4 will measure


@dataclass(frozen=True)
class RunSpec:
    """One planned run, for --dry-run."""

    experiment: str
    variant: str
    group: str
    set_name: str
    n_samples: int
    batch_size: int
    workers: int
    rep: int

    @property
    def estimate_seconds(self) -> float:
        speed = 1.0 if self.workers == 1 else self.workers * _EST_PARALLEL_EFFICIENCY
        return max(self.n_samples, 1) * _EST_SECONDS_PER_SAMPLE[self.variant] / speed


def _grid_specs(experiment, set_name, counts, configs, reps) -> list[RunSpec]:
    groups = [g for g in BENCH_GROUPS if counts.get(g)]
    if not groups or not configs:
        return []
    specs = [
        RunSpec(experiment, v, groups[0], set_name, 1, 1, 1, 0)  # warm-ups
        for v in dict.fromkeys(v for v, _, _ in configs)
    ]
    for rep in range(1, reps + 1):
        for v, b, w in configs:
            specs += [RunSpec(experiment, v, g, set_name, counts[g], b, w, rep) for g in groups]
    return specs


def plan_runs(
    phase: str,
    *,
    counts: dict[str, int],
    scale_counts: dict[str, int],
    reps: dict[str, int],
    variant_filter: str | None = None,
    batch_sizes: Sequence[int] = (10, 20, 50),
    workers_list: Sequence[int] = (1, 2, 4),
    best: tuple[str, int] = ("C", 20),
    scale_workers: int = 4,
    floor_reps: int = 5,
    decompose_each: int = 5,
) -> list[RunSpec]:
    """The runs a phase would execute, without running anything (pure; used by --dry-run)."""
    if phase == "all":
        return [
            spec
            for name in ("env", "decompose", "variants", "workers", "scale")
            for spec in plan_runs(
                name, counts=counts, scale_counts=scale_counts, reps=reps,
                variant_filter=variant_filter, batch_sizes=batch_sizes,
                workers_list=workers_list, best=best, scale_workers=scale_workers,
                floor_reps=floor_reps, decompose_each=decompose_each,
            )
        ]  # fmt: skip
    if phase == "env":
        return [RunSpec("E0", "env", "-", "-", 0, 1, 1, 1)]
    if phase == "decompose":
        specs = [RunSpec("E2", "floor", "-", "-", 0, 1, 1, r) for r in range(1, floor_reps + 1)]
        singles = [
            RunSpec("E2", "B", g, "spike", 1, 1, 1, rep)
            for rep in range(1, reps["decompose"] + 1)
            for g in BENCH_GROUPS
            for _ in range(min(counts.get(g, 0), 2 * decompose_each))
        ]
        warmup = [RunSpec("E2", "B", singles[0].group, "spike", 1, 1, 1, 0)] if singles else []
        return specs + warmup + singles
    if phase == "variants":
        configs = [("A", 1, 1), ("B", 1, 1)] + [("C", n, 1) for n in batch_sizes]
        if variant_filter:
            configs = [c for c in configs if c[0] == variant_filter]
        return _grid_specs("E3", "spike", counts, configs, reps["variants"])
    if phase in ("workers", "scale"):
        w_list = workers_list if phase == "workers" else (scale_workers,)
        configs = [("A", 1, w) for w in w_list] + [(best[0], best[1], w) for w in w_list]
        if phase == "workers":
            return _grid_specs("E4", "spike", counts, configs, reps["workers"])
        return _grid_specs("E5", "scale", scale_counts, configs, reps["scale"])
    raise ValueError(f"unknown phase: {phase!r}")


def format_plan(specs: Sequence[RunSpec], done: frozenset = frozenset(), xmx: str = "4g") -> str:
    """A readable run list plus the total of runs and the rough time estimate."""
    lines = [
        f"{'exp':<4} {'var':<5} {'group':<7} {'set':<6} {'n':>4} {'batch':>5} {'w':>2} "
        f"{'rep':>3} {'est s':>7}"
    ]
    total, runs = 0.0, 0
    for sp in specs:
        skip = (
            sp.rep >= 1
            and sp.variant not in ("env", "floor")
            and config_key(
                sp.variant, sp.group, sp.set_name, sp.workers, sp.batch_size, xmx, sp.rep
            )
            in done
        )
        est = sp.estimate_seconds
        mark = "  (skip: resume)" if skip else ""
        lines.append(
            f"{sp.experiment:<4} {sp.variant:<5} {sp.group:<7} {sp.set_name:<6} {sp.n_samples:>4} "
            f"{sp.batch_size:>5} {sp.workers:>2} {sp.rep:>3} {est:>7.0f}{mark}"
        )
        if not skip:
            total += est
            runs += 1
    lines.append(
        f"{runs} runs to execute, rough estimate {total / 3600:.1f} h "
        f"(per-sample guesses A 9 s, B 8 s, C 3.5 s; parallel efficiency assumed 0.7; "
        f"NOT a measurement)"
    )
    return "\n".join(lines)


def _describe_best(best: tuple[str, int], from_data: bool) -> str:
    source = "from E3 results" if from_data else "DEFAULT, no E3 results yet"
    return f"best container variant for workers/scale: {best[0]} b={best[1]} ({source})"


def _int_list(text: str) -> tuple[int, ...]:
    """argparse type: '10,20,50' -> (10, 20, 50); every value must be a positive integer."""
    try:
        values = tuple(int(x) for x in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a comma-separated integer list: {text!r}") from None
    if not values or any(v < 1 for v in values):
        raise argparse.ArgumentTypeError(f"batch sizes must be >= 1: {text!r}")
    return values


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Joern extraction benchmark (W2-P2-05)")
    ap.add_argument(
        "--phase",
        choices=["env", "decompose", "variants", "workers", "scale", "all"],
        required=True,
    )
    ap.add_argument(
        "--variant", choices=["A", "B", "C"], help="run only this variant in --phase variants"
    )
    ap.add_argument(
        "--batch-sizes",
        type=_int_list,
        default=(10, 20, 50),
        help="variant C batch sizes, comma separated (default 10,20,50)",
    )
    ap.add_argument(
        "--workers",
        type=_int_list,
        default=(1, 2, 4),
        help="worker counts for --phase workers, comma separated (default 1,2,4)",
    )
    ap.add_argument("--image", default=DEFAULT_DOCKER_IMAGE)
    ap.add_argument("--out", default=str(BENCHMARK_DIR), help="folder for results and json")
    ap.add_argument(
        "--work-dir",
        default=str(Path(tempfile.gettempdir()) / "shield_bench"),
        help="scratch folder for job files; keep it OUTSIDE OneDrive (plan risk R9)",
    )
    ap.add_argument("--notes", default="", help="e.g. 'plugged in, high performance, apps closed'")
    ap.add_argument("--xmx", default="4g")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument(
        "--reps",
        type=int,
        help="repetitions (default per phase: decompose 1, variants 3, workers 2, scale 1)",
    )
    ap.add_argument("--group", choices=list(BENCH_GROUPS), help="only this group")
    ap.add_argument("--limit", type=int, help="run only the first N samples per group (hand tests)")
    ap.add_argument("--scale-per-group", type=int, default=200, help="size of the scale set (E5)")
    ap.add_argument("--no-warmup", action="store_true")
    ap.add_argument("--keep", action="store_true", help="keep job folders for inspection")
    ap.add_argument("--resume", action="store_true", help="skip configs already in results.csv")
    ap.add_argument("--dry-run", action="store_true", help="print the run list, run nothing")
    args = ap.parse_args(argv)

    out = Path(args.out).resolve()
    work = Path(args.work_dir).resolve()
    print(f"work dir: {work}\nresults : {out}")
    reps_default = {"decompose": 1, "variants": 3, "workers": 2, "scale": 1}
    reps = {k: args.reps if args.reps is not None else v for k, v in reps_default.items()}

    spike_all = load_spike_samples() if args.phase != "env" else []
    samples = [s for s in spike_all if not args.group or s.group == args.group]
    samples = _limit_per_group(samples, args.limit)

    if args.dry_run:
        counts = dict(Counter(s.group for s in samples))
        n_scale = min(args.scale_per_group, args.limit or args.scale_per_group)
        scale_counts = {g: n_scale for g in BENCH_GROUPS if not args.group or g == args.group}
        best, from_data = pick_best_config(out)
        done = (
            completed_keys(read_rows(out / "results.csv"))
            if args.resume and (out / "results.csv").exists()
            else set()
        )
        specs = plan_runs(
            args.phase, counts=counts, scale_counts=scale_counts, reps=reps,
            variant_filter=args.variant, batch_sizes=args.batch_sizes,
            workers_list=args.workers, best=best,
        )  # fmt: skip
        print(_describe_best(best, from_data))
        print(format_plan(specs, frozenset(done), args.xmx))
        return 0

    out.mkdir(parents=True, exist_ok=True)
    common = {
        "image": args.image,
        "xmx": args.xmx,
        "timeout": args.timeout,
        "work_dir": work,
        "out_dir": out,
        "warmup": not args.no_warmup,
        "keep": args.keep,
    }
    all_phases = ["env", "decompose", "variants", "workers", "scale"]
    phases = all_phases if args.phase == "all" else [args.phase]

    for phase in phases:
        if phase == "env":
            env = capture_environment(args.image, notes=args.notes)
            path = out / "environment.json"
            path.write_text(json.dumps(env, indent=2) + "\n", encoding="utf-8", newline="\n")
            print(json.dumps(env, indent=2))
            print(f"\nwritten: {path}")
        elif phase == "decompose":
            run_decompose(samples, reps=reps["decompose"], **common)
        elif phase == "variants":
            run_variants(
                samples, reps=reps["variants"], variant_filter=args.variant,
                batch_sizes=args.batch_sizes, resume=args.resume, **common,
            )  # fmt: skip
        elif phase == "workers":
            best, from_data = pick_best_config(out)
            print(_describe_best(best, from_data))
            run_workers(
                samples, best=best, workers_list=args.workers, reps=reps["workers"],
                resume=args.resume, **common,
            )  # fmt: skip
        elif phase == "scale":
            best, from_data = pick_best_config(out)
            print(_describe_best(best, from_data))
            exclude = {s.sha256 for s in spike_all}
            scale = draw_scale_samples(args.scale_per_group, exclude_sha=exclude)
            scale = [s for s in scale if not args.group or s.group == args.group]
            run_workers(
                _limit_per_group(scale, args.limit), best=best, workers_list=(4,),
                reps=reps["scale"], experiment="E5", resume=args.resume, **common,
            )  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
