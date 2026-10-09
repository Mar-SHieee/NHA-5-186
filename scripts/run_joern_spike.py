import re
import shutil
import subprocess
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

TEST_DIR = ROOT / "data" / "interim" / "joern_spike_full"
RESULTS_FILE = ROOT / "data" / "interim" / "joern_spike_results.csv"

DATASETS = {
    "python": ROOT / "data/interim/cvefixes_python_samples_20.parquet",
    "c": ROOT / "data/interim/bigvul_samples_20.parquet",
    "cpp": ROOT / "data/interim/megavul_samples_20.parquet",
}

EXTENSIONS = {
    "python": ".py",
    "c": ".c",
    "cpp": ".cpp",
}

SAMPLE_TIMEOUT = 300
MEMORY_POLL_INTERVAL = 0.25


def memory_to_mib(value):
    """Convert Docker memory strings to MiB."""
    match = re.search(
        r"([\d.]+)\s*(B|KiB|MiB|GiB|KB|MB|GB)",
        value,
        re.IGNORECASE,
    )

    if not match:
        return None

    number = float(match.group(1))
    unit = match.group(2).lower()

    factors = {
        "b": 1 / (1024**2),
        "kib": 1 / 1024,
        "mib": 1,
        "gib": 1024,
        "kb": 1000 / (1024**2),
        "mb": 1000**2 / (1024**2),
        "gb": 1000**3 / (1024**2),
    }

    return number * factors[unit]


def get_container_memory(container_name):
    """Read the current Docker container memory usage."""
    result = subprocess.run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{.MemUsage}}",
            container_name,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    if result.returncode != 0:
        return None

    # Docker usually returns: 150MiB / 7.57GiB
    usage = result.stdout.strip().split("/")[0].strip()

    return memory_to_mib(usage)


def run_sample(language, sample_index, code):
    """Run Joern parsing and graph exports for one sample."""

    sample_name = f"{language}_{sample_index:02d}"
    sample_dir = TEST_DIR / sample_name
    sample_dir.mkdir(parents=True, exist_ok=True)

    extension = EXTENSIONS[language]
    source_file = sample_dir / f"sample{extension}"
    cpg_file = sample_dir / "cpg.bin"
    log_file = sample_dir / "joern.log"

    source_file.write_text(code, encoding="utf-8")

    container_name = f"shield-spike-{language}-{sample_index:02d}"

    # Export directories must not exist before joern-export runs.
    cfg_dir = sample_dir / "cfg_export"
    ddg_dir = sample_dir / "ddg_export"

    command_inside_container = (
        "set -e; "
        f"joern-parse /workspace/sample{extension} "
        "--output /workspace/cpg.bin; "
        "joern-export --repr cfg --format dot "
        "--out /workspace/cfg_export /workspace/cpg.bin; "
        "joern-export --repr ddg --format dot "
        "--out /workspace/ddg_export /workspace/cpg.bin"
    )

    docker_command = [
        "docker",
        "run",
        "--name",
        container_name,
        "--mount",
        f"type=bind,source={sample_dir.resolve()},target=/workspace",
        "shield-joern",
        "sh",
        "-lc",
        command_inside_container,
    ]

    result = {
        "language": language,
        "sample_index": sample_index,
        "parsing_success": False,
        "cfg_success": False,
        "ddg_success": False,
        "pipeline_success": False,
        "processing_seconds": None,
        "peak_container_memory_mib": None,
        "error": "",
    }

    start = time.perf_counter()
    peak_memory = None
    timed_out = False

    try:
        # Save logs to a file to avoid filling an output pipe.
        with log_file.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                docker_command,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )

            while process.poll() is None:
                try:
                    memory = get_container_memory(container_name)

                    if memory is not None:
                        if peak_memory is None or memory > peak_memory:
                            peak_memory = memory

                except (subprocess.SubprocessError, OSError):
                    pass

                if time.perf_counter() - start > SAMPLE_TIMEOUT:
                    timed_out = True
                    process.kill()
                    break

                time.sleep(MEMORY_POLL_INTERVAL)

            return_code = process.wait()

        result["processing_seconds"] = round(time.perf_counter() - start, 3)
        result["peak_container_memory_mib"] = (
            round(peak_memory, 2) if peak_memory is not None else None
        )

        result["parsing_success"] = cpg_file.exists() and cpg_file.stat().st_size > 0

        result["cfg_success"] = cfg_dir.exists() and any(
            path.is_file() and path.stat().st_size > 0 for path in cfg_dir.glob("*.dot")
        )

        result["ddg_success"] = ddg_dir.exists() and any(
            path.is_file() and path.stat().st_size > 0 for path in ddg_dir.glob("*.dot")
        )

        result["pipeline_success"] = (
            return_code == 0
            and result["parsing_success"]
            and result["cfg_success"]
            and result["ddg_success"]
        )

        if timed_out:
            result["error"] = f"Timed out after {SAMPLE_TIMEOUT} seconds"
        elif return_code != 0:
            result["error"] = log_file.read_text(encoding="utf-8", errors="replace")[-1500:]
        elif not result["pipeline_success"]:
            result["error"] = "One or more expected outputs were missing or empty"

    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["processing_seconds"] = round(time.perf_counter() - start, 3)

    finally:
        # Remove the stopped or timed-out container.
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            text=True,
            timeout=30,
        )

    print(
        f"{language:6} sample {sample_index:02d} | "
        f"parse={result['parsing_success']} | "
        f"cfg={result['cfg_success']} | "
        f"ddg={result['ddg_success']} | "
        f"time={result['processing_seconds']}s | "
        f"memory={result['peak_container_memory_mib']} MiB"
    )

    return result


def main():
    # This directory contains only generated test artifacts.
    # Remove it so old outputs cannot be mistaken for new results.
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)

    TEST_DIR.mkdir(parents=True)

    results = []

    for language, dataset_path in DATASETS.items():
        print(f"\n{'=' * 55}")
        print(f"Testing {language}: {dataset_path.name}")
        print(f"{'=' * 55}")

        df = pd.read_parquet(dataset_path)

        if len(df) != 20:
            raise ValueError(f"{dataset_path} has {len(df)} rows; expected 20")

        if "code" not in df.columns:
            raise ValueError(f"Missing 'code' column in {dataset_path}")

        for index, code in enumerate(df["code"], start=1):
            if not isinstance(code, str) or not code.strip():
                results.append(
                    {
                        "language": language,
                        "sample_index": index,
                        "parsing_success": False,
                        "cfg_success": False,
                        "ddg_success": False,
                        "pipeline_success": False,
                        "processing_seconds": 0,
                        "peak_container_memory_mib": None,
                        "error": "Empty or invalid source code",
                    }
                )
                continue

            try:
                results.append(run_sample(language, index, code))
            except Exception as exc:
                # Keep the full run going if one sample fails.
                results.append(
                    {
                        "language": language,
                        "sample_index": index,
                        "parsing_success": False,
                        "cfg_success": False,
                        "ddg_success": False,
                        "pipeline_success": False,
                        "processing_seconds": None,
                        "peak_container_memory_mib": None,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

                print(f"{language} sample {index:02d} " f"failed: {exc}")

        # Save partial results after each language.
        pd.DataFrame(results).to_csv(RESULTS_FILE, index=False)

    results_df = pd.DataFrame(results)
    results_df.to_csv(RESULTS_FILE, index=False)

    print("\n\n========== FINAL SUMMARY ==========")

    summary = results_df.groupby("language").agg(
        samples=("sample_index", "count"),
        parsing_successes=("parsing_success", "sum"),
        cfg_successes=("cfg_success", "sum"),
        ddg_successes=("ddg_success", "sum"),
        full_pipeline_successes=("pipeline_success", "sum"),
        mean_processing_seconds=("processing_seconds", "mean"),
        max_container_memory_mib=("peak_container_memory_mib", "max"),
    )

    summary["pipeline_success_rate_pct"] = (
        summary["full_pipeline_successes"] / summary["samples"] * 100
    )

    print(summary.round(2).to_string())
    print(f"\nDetailed results: {RESULTS_FILE}")


if __name__ == "__main__":
    main()
