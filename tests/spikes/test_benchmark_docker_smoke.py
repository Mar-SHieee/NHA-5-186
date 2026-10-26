"""Docker smoke test for the benchmark runner (W2-P2-05, step 3.8).

Runs variant B for real on `tests/fixtures/joern/calls.py`. It is SKIPPED when the `docker`
program is missing, the Docker daemon is not running, or the `shield-joern` image is not built
(so CI, which has no Docker, stays green). Everything else in tests/spikes uses a fake docker.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.spikes.joern import benchmark_extraction as be
from scripts.spikes.joern.benchmark_core import Sample
from shield_core.extraction.joern_extractor import DEFAULT_DOCKER_IMAGE

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "joern" / "calls.py"


@pytest.fixture(scope="module")
def docker_image() -> str:
    """The image name, or a skip with the reason (checked lazily, not at import time)."""
    if shutil.which("docker") is None:
        pytest.skip("docker is not installed")
    try:
        probe = subprocess.run(
            ["docker", "image", "inspect", DEFAULT_DOCKER_IMAGE],
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        pytest.skip("docker did not answer (is Docker Desktop running?)")
    if probe.returncode != 0:
        pytest.skip(f"image {DEFAULT_DOCKER_IMAGE!r} is missing or the daemon is not running")
    return DEFAULT_DOCKER_IMAGE


def test_variant_b_on_a_real_container_gives_one_ok_sample_and_a_numeric_peak(
    docker_image, tmp_path
):
    code = FIXTURE.read_text(encoding="utf-8")
    sample = Sample("python_smoke_001", "python", ".py", code, "smoke", "fixture", 0)

    out = be.run_variant_b(
        [sample],
        image=docker_image,
        xmx="2g",
        timeout=300,
        work_dir=tmp_path,
        run_id="smoke-b",
    )

    assert len(out.results) == 1
    result = out.results[0]
    assert result.ok, f"extraction failed: {result.failure_class}; stderr: {out.stderr_tail}"
    assert result.nodes and result.nodes > 0
    assert result.edges and result.edges > 0
    assert out.peak_method == "cgroup"
    assert isinstance(out.peak_mib, float) and out.peak_mib > 0
    assert out.parse_seconds and out.parse_seconds > 0
    assert out.export_seconds and out.export_seconds > 0
    assert out.wall_seconds >= out.parse_seconds
