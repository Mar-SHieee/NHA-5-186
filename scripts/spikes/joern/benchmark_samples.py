"""Sample sets for the Joern extraction benchmark (W2-P2-05).

Two sets, so that results are comparable with the old spike AND tested on more data:
  * spike : the 60 rows of the three `*_samples_20.parquet` files, in the spike's order.
  * scale : N new rows per group (default 200, seed 43) from the deduped files, never a
            row whose code is already in the spike set.

Run `python -m scripts.spikes.joern.benchmark_samples` to write the manifest and print the
size statistics (they go into the plan's STATE and into the report).
"""

from __future__ import annotations

import csv
import warnings
from collections import defaultdict
from collections.abc import Collection, Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.spikes.joern.benchmark_core import BENCH_GROUPS, Sample, summarize
from shield_core.extraction.graph_extractor import normalize_code
from shield_core.paths import BENCHMARK_DIR, INTERIM_DIR

# group -> (source name, spike file, deduped file). Same mapping as run_joern_spike.py.
SOURCES = {
    "python": ("cvefixes_python", "cvefixes_python_samples_20.parquet"),
    "c": ("bigvul", "bigvul_samples_20.parquet"),
    "cpp": ("megavul", "megavul_samples_20.parquet"),
}
SPIKE_FILES = {g: fname for g, (_, fname) in SOURCES.items()}
DEDUPED_FILES = {g: f"{src}_deduped.parquet" for g, (src, _) in SOURCES.items()}

SPIKE_SEED_NOTE = "spike rows keep the order of their parquet file"
DEFAULT_SCALE_SEED = 43  # the spike used 42; a different seed keeps the draw independent
DEFAULT_SCALE_PER_GROUP = 200

MANIFEST_COLUMNS = [
    "sample_id",
    "group",
    "set_name",
    "extension",
    "source",
    "row_index",
    "sha256",
    "n_chars",
    "n_lines",
]


def _is_usable(code: object) -> bool:
    """Real code only: a string with something other than whitespace in it."""
    return isinstance(code, str) and bool(code.strip())


def _make_id(group: str, set_name: str, number: int) -> str:
    return f"{group}_{set_name}_{number:03d}"  # ASCII only, safe as a file name


def load_spike_samples(interim_dir: Path = INTERIM_DIR) -> list[Sample]:
    """The 60 spike rows, group by group (python, c, cpp), in file order."""
    samples: list[Sample] = []
    for group, (source, fname) in SOURCES.items():
        path = Path(interim_dir) / fname
        if not path.exists():
            raise FileNotFoundError(
                f"{path} is missing: regenerate the *_samples_20 files "
                "(shield_core/datasets/samples/) before building the spike set"
            )
        ext = BENCH_GROUPS[group][1]
        codes = pd.read_parquet(path, columns=["code"])["code"].tolist()
        number = 0
        for position, code in enumerate(codes):
            if not _is_usable(code):
                continue
            number += 1
            samples.append(
                Sample(
                    _make_id(group, "spike", number), group, ext, code, "spike", source, position
                )
            )
    return samples


def draw_scale_samples(
    n_per_group: int = DEFAULT_SCALE_PER_GROUP,
    seed: int = DEFAULT_SCALE_SEED,
    exclude_sha: Collection[str] = frozenset(),
    interim_dir: Path = INTERIM_DIR,
) -> list[Sample]:
    """`n_per_group` rows per group from the deduped files, seeded, avoiding `exclude_sha`.

    Walks a seeded random permutation of the rows and keeps the first `n_per_group` usable,
    non-excluded ones. That is a uniform random sample of the eligible rows, and it only
    hashes the rows it visits (the C/C++ files have hundreds of thousands of rows).
    No length filter: the natural size distribution (long tail included) is the point.
    """
    samples: list[Sample] = []
    for group, (source, _) in SOURCES.items():
        path = Path(interim_dir) / DEDUPED_FILES[group]
        if not path.exists():
            raise FileNotFoundError(f"{path} is missing: run the dedupe step first (README §3)")
        ext = BENCH_GROUPS[group][1]
        codes = pd.read_parquet(path, columns=["code"])["code"].tolist()
        order = np.random.RandomState(seed).permutation(len(codes))

        picked: list[Sample] = []
        for position in order:
            code = codes[int(position)]
            if not _is_usable(code):
                continue
            candidate = Sample(
                "", group, ext, code, "scale", source, int(position)
            )  # id is assigned below
            if candidate.sha256 in exclude_sha:
                continue
            picked.append(candidate)
            if len(picked) == n_per_group:
                break

        if len(picked) < n_per_group:
            warnings.warn(
                f"{group}: only {len(picked)} usable rows available, wanted {n_per_group}",
                UserWarning,
                stacklevel=2,
            )
        for number, s in enumerate(picked, start=1):
            samples.append(
                Sample(
                    _make_id(group, "scale", number),
                    s.group,
                    s.extension,
                    s.code,
                    s.set_name,
                    s.source,
                    s.row_index,
                )
            )
    return samples


def write_job_dir(job_dir: Path, samples: Sequence[Sample]) -> list[Path]:
    """Write one file per sample (`<sample_id><ext>`) with LF line endings; return the paths.

    The text is normalized first and written with newline="\\n": otherwise Windows would
    turn every "\\n" into "\\r\\n", which changes the hash and the parse.
    """
    ids = [s.sample_id for s in samples]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate sample_id in job: two samples would overwrite each other")
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for s in samples:
        path = job_dir / f"{s.sample_id}{s.extension}"
        with path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(normalize_code(s.code))
        paths.append(path)
    return paths


def write_manifest(path: Path, samples: Sequence[Sample]) -> None:
    """One row per sample (no code): enough to find and verify every sample later."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for s in samples:
            writer.writerow(
                {
                    "sample_id": s.sample_id,
                    "group": s.group,
                    "set_name": s.set_name,
                    "extension": s.extension,
                    "source": s.source,
                    "row_index": s.row_index,
                    "sha256": s.sha256,
                    "n_chars": s.n_chars,
                    "n_lines": s.n_lines,
                }
            )


def describe_lines(samples: Sequence[Sample]) -> dict[str, dict]:
    """Per group: n, min, median, p95, max of the function length in lines."""
    by_group: dict[str, list[float]] = defaultdict(list)
    for s in samples:
        by_group[s.group].append(s.n_lines)
    return {group: summarize(values) for group, values in by_group.items()}


def main() -> None:
    spike = load_spike_samples()
    scale = draw_scale_samples(exclude_sha={s.sha256 for s in spike})
    everything = spike + scale
    manifest = BENCHMARK_DIR / "samples_manifest.csv"
    write_manifest(manifest, everything)
    print(f"manifest written: {manifest}  ({len(everything)} samples)")
    for set_name, subset in (("spike", spike), ("scale", scale)):
        print(f"\n[{set_name}] {len(subset)} samples; function length in lines")
        for group, st in describe_lines(subset).items():
            print(
                f"  {group:<7} n={st['n']:<4} min={st['min']:.0f} "
                f"median={st['median']:.0f} p95={st['p95']:.0f} max={st['max']:.0f}"
            )


if __name__ == "__main__":
    main()
