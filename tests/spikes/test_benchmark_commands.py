"""Tests for the pure command builders in benchmark_extraction.py (W2-P2-05). No Docker."""

import shutil
import subprocess
import sys

import pytest

from scripts.spikes.joern import benchmark_extraction as be
from scripts.spikes.joern.benchmark_core import parse_markers

FILES = ["python_spike_001.py", "python_spike_002.py", "python_spike_003.py"]


def _lines(script: str) -> list[str]:
    return [ln.strip() for ln in script.splitlines() if ln.strip()]


# ----------------------------------------------------------------------------- variant B


def test_variant_b_has_two_joern_commands_per_file_with_the_right_frontend():
    script = be.build_batch_script("B", FILES, "pythonsrc", 1)
    assert script.count("joern-parse ") == 3
    assert script.count("joern-export ") == 3
    assert script.count("--language pythonsrc") == 3
    # same flags as the production JoernExtractor
    assert script.count("--repr all --format graphml") == 3


def test_variant_b_marks_parse_and_export_time_per_file():
    script = be.build_batch_script("B", FILES, "pythonsrc", 1)
    for k in (1, 2, 3):
        assert f"@@T parse_{k} " in script
        assert f"@@T export_{k} " in script


# ----------------------------------------------------------------------------- variant C


def test_variant_c_has_one_parse_and_one_export_per_batch():
    files = [f"c_spike_{i:03d}.c" for i in range(1, 8)]  # 7 files, batch 3 -> 3 batches
    script = be.build_batch_script("C", files, "newc", 3)
    assert script.count("joern-parse ") == 3
    assert script.count("joern-export ") == 3
    assert script.count("mkdir ") == 3
    assert "batch_1" in script and "batch_3" in script and "batch_4" not in script


def test_variant_c_batch_size_larger_than_list_is_a_single_batch():
    script = be.build_batch_script("C", FILES, "pythonsrc", 50)
    assert script.count("joern-parse ") == 1


# ----------------------------------------------------------------------------- common rules


@pytest.mark.parametrize("variant", ["B", "C"])
def test_peak_marker_is_the_last_line_and_tries_both_cgroup_versions(variant):
    script = be.build_batch_script(variant, FILES, "pythonsrc", 2)
    last = _lines(script)[-1]
    assert last.startswith('echo "@@PEAK')
    assert "/sys/fs/cgroup/memory.peak" in last
    assert "memory.max_usage_in_bytes" in last
    assert "NA" in last


@pytest.mark.parametrize("variant", ["B", "C"])
def test_script_never_aborts_on_the_first_failure(variant):
    script = be.build_batch_script(variant, FILES, "pythonsrc", 2)
    assert "set -e" not in script
    assert "exit" not in script
    assert "@@FAIL" in script


@pytest.mark.parametrize("variant", ["B", "C"])
def test_file_names_are_single_quoted(variant):
    script = be.build_batch_script(variant, ["python_spike_001.py"], "pythonsrc", 1)
    assert "'python_spike_001.py'" in script


@pytest.mark.parametrize(
    "bad", ["a b.py", "x;rm -rf.py", "$(id).py", "a'b.py", "../up.py", "", "dir/x.py"]
)
def test_unsafe_file_names_are_rejected(bad):
    with pytest.raises(ValueError, match="file name"):
        be.build_batch_script("B", [bad], "pythonsrc", 1)


def test_bad_arguments_are_rejected():
    with pytest.raises(ValueError, match="variant"):
        be.build_batch_script("A", FILES, "pythonsrc", 1)  # A runs on the host, no script
    with pytest.raises(ValueError, match="batch"):
        be.build_batch_script("C", FILES, "pythonsrc", 0)
    with pytest.raises(ValueError, match="no files"):
        be.build_batch_script("B", [], "pythonsrc", 1)
    with pytest.raises(ValueError, match="frontend"):
        be.build_batch_script("B", FILES, "python; ls", 1)


# ----------------------------------------------------------------------------- docker command


def test_docker_command_has_all_required_parts():
    cmd = be.build_docker_command("shield-joern", "/tmp/job", "shield-bench-w1", "4g", "echo hi")
    assert cmd[:2] == ["docker", "run"]
    assert "--rm" in cmd
    assert cmd[cmd.index("--name") + 1] == "shield-bench-w1"
    assert cmd[cmd.index("--mount") + 1] == "type=bind,source=/tmp/job,target=/workspace/job"
    assert cmd[cmd.index("-w") + 1] == "/workspace/job"
    assert cmd[cmd.index("-e") + 1] == "JAVA_OPTS=-Xmx4g"
    assert cmd[-4:] == ["shield-joern", "bash", "-c", "echo hi"]


@pytest.mark.parametrize("bad", ["shield-bench-a b", "shield-bench-a;ls", "other-name", ""])
def test_container_names_must_be_safe_and_start_with_shield_bench(bad):
    with pytest.raises(ValueError, match="container name"):
        be.build_docker_command("shield-joern", "/tmp/job", bad, "4g", "true")


@pytest.mark.parametrize("bad", ["4", "g4", "4 g", "4g;ls", "-1g"])
def test_xmx_must_look_like_a_java_heap_size(bad):
    with pytest.raises(ValueError, match="xmx"):
        be.build_docker_command("shield-joern", "/tmp/job", "shield-bench-w1", bad, "true")


def test_job_dir_with_a_comma_is_rejected_because_mount_syntax_splits_on_commas():
    with pytest.raises(ValueError, match="job_dir"):
        be.build_docker_command("shield-joern", "/tmp/a,b", "shield-bench-w1", "4g", "true")


# ----------------------------------------------------------------------------- real bash run

needs_bash = pytest.mark.skipif(
    shutil.which("bash") is None or sys.platform == "win32",
    reason="runs the generated script with fake joern tools; needs a POSIX bash",
)


def _fake_tools(tmp_path, failing: str):
    """joern-parse fails for one file name; both tools otherwise create their output."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "joern-parse").write_text(
        '#!/bin/bash\n[[ "$1" == *' + failing + '* ]] && exit 3\n: > "${@: -1}"\nexit 0\n'
    )
    (bin_dir / "joern-export").write_text('#!/bin/bash\nmkdir -p "${@: -1}"\nexit 0\n')
    for tool in bin_dir.iterdir():
        tool.chmod(0o755)
    return bin_dir


@needs_bash
def test_a_failing_file_does_not_stop_the_loop(tmp_path):
    job = tmp_path / "job"
    job.mkdir()
    for name in FILES:
        (job / name).write_text("x = 1\n")
    script = be.build_batch_script("B", FILES, "pythonsrc", 1)
    env = {"PATH": f"{_fake_tools(tmp_path, 'spike_002')}:/usr/bin:/bin"}
    proc = subprocess.run(
        ["bash", "-c", script], cwd=job, env=env, capture_output=True, text=True, timeout=30
    )
    markers = parse_markers(proc.stdout)
    assert markers.failures == {"2": 3}  # file 2 failed with rc 3 ...
    assert "parse_1" in markers.timings and "parse_3" in markers.timings  # ... 1 and 3 ran
    assert "export_3" in markers.timings
    assert "export_2" not in markers.timings
    assert markers.peak_bytes is None or markers.peak_bytes > 0  # last line was reached
    assert proc.stdout.strip().splitlines()[-1].startswith("@@PEAK")


# ----------------------------------------------------------------------------- environment (E0)


def test_parse_docker_info_reads_cpus_and_memory():
    assert be.parse_docker_info("24 8188317696\n") == {
        "docker_cpus": 24,
        "docker_mem_bytes": 8188317696,
    }


@pytest.mark.parametrize("bad", ["", "24", "x y", "24 8188317696 extra"])
def test_parse_docker_info_returns_none_values_for_garbage(bad):
    assert be.parse_docker_info(bad) == {"docker_cpus": None, "docker_mem_bytes": None}


@pytest.mark.parametrize(
    "path, expected",
    [
        (r"C:\Users\eyada\OneDrive\Desktop\SHIELD", True),
        ("/home/me/onedrive - uni/shield", True),
        (r"C:\Users\eyada\code\SHIELD", False),
    ],
)
def test_onedrive_detection(path, expected):
    assert be.is_inside_onedrive(path) is expected


def test_capture_environment_uses_the_given_runner_and_survives_docker_failures():
    class Done:
        def __init__(self, rc, out):
            self.returncode, self.stdout, self.stderr = rc, out, ""

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["docker", "info"]:
            return Done(0, "24 8188317696\n")
        if cmd[:3] == ["docker", "image", "inspect"]:
            return Done(0, "sha256:51394b312f9a\n")
        return Done(1, "")

    env = be.capture_environment("shield-joern", notes="plugged in", run=fake_run)
    assert env["docker_cpus"] == 24
    assert env["image_id"] == "sha256:51394b312f9a"
    assert env["joern_version"] == "4.0.647"
    assert env["notes"] == "plugged in"
    assert env["cpu_count"] >= 1
    assert "timestamp_utc" in env and "repo_inside_onedrive" in env

    def docker_down(cmd, **kwargs):
        raise FileNotFoundError("docker")

    env = be.capture_environment("shield-joern", run=docker_down)  # must not raise
    assert env["docker_cpus"] is None and env["image_id"] is None
