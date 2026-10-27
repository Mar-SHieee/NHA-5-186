"""Tests for scripts/spikes/joern/benchmark_samples.py (W2-P2-05). Synthetic data only."""

import csv
import re

import pandas as pd
import pytest

from scripts.spikes.joern import benchmark_samples as bs
from scripts.spikes.joern.benchmark_core import BENCH_GROUPS, Sample


def _frame(prefix: str, n: int) -> pd.DataFrame:
    return pd.DataFrame({"code": [f"int {prefix}{i}(void) {{ return {i}; }}\n" for i in range(n)]})


@pytest.fixture
def interim(tmp_path):
    """A fake data/interim with spike files (3 rows each) and deduped files (30 rows each)."""
    for group, fname in bs.SPIKE_FILES.items():
        _frame(group, 3).to_parquet(tmp_path / fname)
    for group, fname in bs.DEDUPED_FILES.items():
        spike = _frame(group, 3)  # the spike rows are also present in the deduped file
        rest = _frame(group + "_other", 27)
        pd.concat([spike, rest], ignore_index=True).to_parquet(tmp_path / fname)
    return tmp_path


# ----------------------------------------------------------------------------- spike set


def test_spike_set_keeps_file_order_and_groups(interim):
    samples = bs.load_spike_samples(interim)
    assert len(samples) == 9
    assert [s.group for s in samples] == ["python"] * 3 + ["c"] * 3 + ["cpp"] * 3
    assert [s.sample_id for s in samples[:3]] == [
        "python_spike_001",
        "python_spike_002",
        "python_spike_003",
    ]
    assert samples[0].code.startswith("int python0(")  # row order preserved
    assert all(s.set_name == "spike" for s in samples)
    assert {s.extension for s in samples if s.group == "c"} == {".c"}


def test_spike_set_missing_file_raises_with_a_clear_message(tmp_path):
    with pytest.raises(FileNotFoundError, match="samples_20"):
        bs.load_spike_samples(tmp_path)


# ----------------------------------------------------------------------------- scale set


def test_scale_draw_is_deterministic(interim):
    a = bs.draw_scale_samples(5, seed=43, exclude_sha=frozenset(), interim_dir=interim)
    b = bs.draw_scale_samples(5, seed=43, exclude_sha=frozenset(), interim_dir=interim)
    assert [s.sample_id for s in a] == [s.sample_id for s in b]
    assert [s.code for s in a] == [s.code for s in b]
    c = bs.draw_scale_samples(5, seed=44, exclude_sha=frozenset(), interim_dir=interim)
    assert [s.code for s in a] != [s.code for s in c]


def test_scale_excludes_spike_hashes(interim):
    spike = bs.load_spike_samples(interim)
    exclude = frozenset(s.sha256 for s in spike)
    scale = bs.draw_scale_samples(27, seed=43, exclude_sha=exclude, interim_dir=interim)
    assert len(scale) == 81  # all 27 non-spike rows of each group, nothing from the spike
    assert not ({s.sha256 for s in scale} & exclude)


def test_scale_gives_n_per_group_and_records_row_index(interim):
    scale = bs.draw_scale_samples(5, seed=43, exclude_sha=frozenset(), interim_dir=interim)
    for group in BENCH_GROUPS:
        rows = [s for s in scale if s.group == group]
        assert len(rows) == 5
        assert all(s.set_name == "scale" for s in rows)
        assert len({s.row_index for s in rows}) == 5  # distinct source rows


def test_scale_warns_and_returns_fewer_when_not_enough_rows(interim):
    with pytest.warns(UserWarning, match="only 30"):
        scale = bs.draw_scale_samples(50, seed=43, exclude_sha=frozenset(), interim_dir=interim)
    assert len(scale) == 90  # 30 per group


def test_empty_and_non_string_code_is_dropped(tmp_path):
    for fname in bs.SPIKE_FILES.values():
        _frame("s", 1).to_parquet(tmp_path / fname)
    messy = pd.DataFrame({"code": ["", "   \n", None, "int ok(void){return 1;}\n"] * 3})
    for fname in bs.DEDUPED_FILES.values():
        messy.to_parquet(tmp_path / fname)
    with pytest.warns(UserWarning):
        scale = bs.draw_scale_samples(10, seed=1, exclude_sha=frozenset(), interim_dir=tmp_path)
    assert scale  # something survived
    assert all(isinstance(s.code, str) and s.code.strip() for s in scale)


def test_sample_ids_are_unique_and_filename_safe(interim):
    spike = bs.load_spike_samples(interim)
    scale = bs.draw_scale_samples(10, seed=43, exclude_sha=frozenset(), interim_dir=interim)
    ids = [s.sample_id for s in spike + scale]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[a-z]+_(spike|scale)_\d{3}", i) for i in ids)


# ----------------------------------------------------------------------------- files on disk


def test_written_files_have_lf_endings_and_expected_names(tmp_path):
    samples = [
        Sample("python_spike_001", "python", ".py", "a = 1\r\nb = 2\r\n", "spike", "x", 0),
        Sample("c_spike_001", "c", ".c", "int f(){\rreturn 1;}\r", "spike", "y", 1),
    ]
    paths = bs.write_job_dir(tmp_path / "job", samples)
    assert [p.name for p in paths] == ["python_spike_001.py", "c_spike_001.c"]
    for p in paths:
        assert b"\r" not in p.read_bytes()
    assert paths[0].read_text(encoding="utf-8") == "a = 1\nb = 2\n"


def test_write_job_dir_rejects_duplicate_ids(tmp_path):
    s = Sample("python_spike_001", "python", ".py", "x = 1\n", "spike", "x", 0)
    with pytest.raises(ValueError, match="duplicate"):
        bs.write_job_dir(tmp_path / "job", [s, s])


def test_manifest_columns_and_values(tmp_path):
    s = Sample("python_spike_001", "python", ".py", "a = 1\nb = 2\n", "spike", "cvefixes", 7)
    path = tmp_path / "out" / "samples_manifest.csv"
    bs.write_manifest(path, [s])
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == bs.MANIFEST_COLUMNS
    assert rows[0]["sample_id"] == "python_spike_001"
    assert rows[0]["row_index"] == "7"
    assert rows[0]["n_lines"] == "2"
    assert rows[0]["sha256"] == s.sha256


# ----------------------------------------------------------------------------- statistics


def test_describe_lines_per_group():
    samples = [
        Sample(f"python_spike_{i:03d}", "python", ".py", "x\n" * n, "spike", "s", i)
        for i, n in enumerate([1, 2, 3, 4], start=1)
    ]
    stats = bs.describe_lines(samples)
    assert stats["python"]["n"] == 4
    assert stats["python"]["median"] == 2.5
    assert stats["python"]["max"] == 4
