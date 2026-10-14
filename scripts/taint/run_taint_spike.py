"""Taint spike driver (W1-P2-03): run the YAML-defined Joern taint query over the fixtures and
compare the result with each fixture's `EXPECT:` line.

    python -m scripts.taint.run_taint_spike --lang cpp                  # runs Docker + Joern
    python -m scripts.taint.run_taint_spike --lang cpp --print-script   # only print the Scala
    python -m scripts.taint.run_taint_spike --lang cpp --from-output out.txt

Verdicts (one row per sink call, not per fixture):
    OK            found what the EXPECT line says
    KNOWN-MISS    a documented Joern limit (KNOWN_MISSES below, explained in docs/taint_spike.md)
    KNOWN-FP      a documented false positive: Joern reports a flow the code does not have
    NOW-OK        a documented miss or false positive that no longer happens: update the doc,
                  remove the entry
    UNEXPECTED    anything else, including a wrong sanitizer flag; the exit code is 1
    SKIP          the fixture has no EXPECT line (c10 only lists argument indices)

STATUS: `--script` mode with `--param` is VERIFIED in our image (Joern 4.0.647, cpp run: 41 sources,
38 sinks, 26 flows at depth 4 and 28 at depth 8). `--print-script` and `--from-output` remain
for machines where Docker is not available.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from languages import registry
from shield_core.taint.joern_queries import Report, build_script, parse_output

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIRS = {"cpp": "c", "python": "python"}

_EXPECT_RE = re.compile(r"EXPECT:\s*(no-flow|flow)\b")

# (file name, sink method) -> why the miss is documented. Every entry is OBSERVED on Joern
# 4.0.647; docs/taint_spike.md, Part B, says what is and is not known about the cause.
KNOWN_MISSES: dict[tuple[str, str], str] = {
    ("py11_attribute.py", "query"): "state written by one method and read by another is invisible",
    ("c07_alias.c", "f_c07"): "alias made BEFORE the write is not followed",
    ("c07c_alias_source.c", "f_c07c"): "write through an alias is not seen at the original",
    ("c16_class_method.cpp", "launch"): "C++ object call is not linked to its method",
    ("c18_cpp_static_call.cpp", "launch_s"): "C++ static call is not linked to its method",
    ("c19_cpp_member_to_member.cpp", "sink_c19"): "C++ member call is not linked to its method",
    ("c21_strncpy.c", "f_c21"): "strncpy does not carry taint into the destination",
    ("c24_copy_functions.c", "f_c24b"): "strncpy does not carry taint (length expression)",
    ("c24_copy_functions.c", "f_c24d"): "strncat does not carry taint",
    ("c24_copy_functions.c", "f_c24g"): "strncpy does not carry taint (constant length)",
}

# Misses that exist only at the default call depth (Python py12b/e: chains of 6 and 5 functions
# are lost at maxCallDepth 4 and recovered at 8, Part A of docs/taint_spike.md). They apply
# only while the driver runs with --max-depth <= DEFAULT_DEPTH.
DEFAULT_DEPTH = 4
KNOWN_DEPTH_MISSES: dict[tuple[str, str], str] = {
    ("py12_depth.py", "handler_py12b"): "chain of 6 functions entered, lost at depth 4",
    ("py12_depth.py", "handler_py12e"): "chain of 5 functions entered, lost at depth 4",
}

# (file name, sink method) -> a flow Joern reports although the code has none.
KNOWN_FALSE_POSITIVES: dict[tuple[str, str], str] = {
    ("py07b_container_precision.py", "handler_py07b"): (
        "a dict is tainted as a whole: reading the safe key still reports a flow"
    ),
}

# (file name, sink method) pairs whose reported flow must pass a sanitizer from the YAML
# (`sanitizer_present`). Every other reached sink must report none. c23 reports only the
# sanitized path, so its flag means "at least one reported path is sanitized".
SANITIZED_SINKS: set[tuple[str, str]] = {
    ("py14_cast_sanitizer.py", "handler_py14"),  # int(...) is visible in the path
    ("c22_realpath.c", "f_c22a"),
    ("c22_realpath.c", "f_c22b"),
    ("c23_branch_sanitizer.c", "f_c23"),
}

# (file name, sink method, sink call) -> expectation that differs from the file's EXPECT line.
SINK_OVERRIDES: dict[tuple[str, str, str], tuple[str, str]] = {
    ("c24_copy_functions.c", "f_c24e", "memcpy(buf, c, 16)"): (
        "no-flow",
        "the length is the constant 16: only the source string is tainted",
    ),
}


@dataclass(frozen=True)
class Row:
    file: str
    method: str
    call: str
    line: str
    expected: str | None
    found: bool
    verdict: str
    note: str = ""
    sanitized: bool = False


def read_expectations(folder: Path) -> dict[str, str]:
    """file name -> 'flow' | 'no-flow', from the EXPECT line in the first lines of each file."""
    result: dict[str, str] = {}
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        head = path.read_text(encoding="utf-8", errors="replace").splitlines()[:6]
        for line in head:
            match = _EXPECT_RE.search(line)
            if match:
                result[path.name] = match.group(1)
                break
    return result


def evaluate(
    report: Report, expectations: dict[str, str], max_depth: int = DEFAULT_DEPTH
) -> list[Row]:
    reached: dict[tuple[str, str, str, str], bool] = {}
    for f in report.flows:
        flow_key = (Path(f.sink.file).name, f.sink.method, f.sink.line, f.sink.call)
        reached[flow_key] = reached.get(flow_key, False) or f.sanitizer_present
    seen: set[tuple[str, str, str, str]] = set()
    rows: list[Row] = []
    for sink in report.sinks:
        key = (Path(sink.file).name, sink.method, sink.line, sink.call)
        if key in seen:  # an `arg_from` sink yields several nodes for one call
            continue
        seen.add(key)
        name, method, line, call = key
        found = key in reached
        sanitized = reached.get(key, False)
        expected = expectations.get(name)
        note = ""
        override = SINK_OVERRIDES.get((name, method, call))
        if override is not None:
            expected, note = override
        if expected is None:
            rows.append(Row(name, method, call, line, None, found, "SKIP", "", sanitized))
            continue
        matches = (expected == "flow") == found
        known = KNOWN_MISSES.get((name, method))
        if known is None and max_depth <= DEFAULT_DEPTH:
            known = KNOWN_DEPTH_MISSES.get((name, method))
        known_fp = KNOWN_FALSE_POSITIVES.get((name, method))
        if matches and known is not None and expected == "flow":
            verdict, note = "NOW-OK", f"documented miss no longer happens ({known})"
        elif matches and known_fp is not None and expected == "no-flow":
            verdict, note = "NOW-OK", f"documented false positive no longer happens ({known_fp})"
        elif matches:
            verdict = "OK"
            if found and sanitized != ((name, method) in SANITIZED_SINKS):
                verdict = "UNEXPECTED"
                note = "sanitizer flag is " + ("set" if sanitized else "not set")
        elif known is not None and expected == "flow" and not found:
            verdict, note = "KNOWN-MISS", known
        elif known_fp is not None and expected == "no-flow" and found:
            verdict, note = "KNOWN-FP", known_fp
        else:
            verdict = "UNEXPECTED"
        rows.append(Row(name, method, call, line, expected, found, verdict, note, sanitized))
    return sorted(rows, key=lambda r: (r.file, r.line, r.call))


def format_table(rows: list[Row]) -> str:
    out = [
        "| file | method | sink call | expected | joern | sanitizer | verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        joern = "flow" if r.found else "no flow"
        verdict = r.verdict + (f" ({r.note})" if r.note else "")
        san = "yes" if r.found and r.sanitized else "-"
        out.append(
            f"| {r.file} | {r.method} | `{r.call}` | {r.expected or '-'} | {joern} | {san} | "
            f"{verdict} |"
        )
    return "\n".join(out)


def summarize(rows: list[Row]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1
    return counts


def run_joern(script: str, fixtures: Path, image: str, timeout: int) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        script_path = Path(tmp) / "taint_query.sc"
        script_path.write_text(script, encoding="utf-8")
        command = [
            "docker", "run", "--rm",
            "-v", f"{fixtures.resolve()}:/workspace/fixtures",
            "-v", f"{script_path}:/workspace/taint_query.sc",
            image, "joern", "--script", "/workspace/taint_query.sc",
            "--param", "inputPath=fixtures",
        ]  # fmt: skip
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    return done.stdout + "\n" + done.stderr


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", default="cpp", choices=sorted(FIXTURE_DIRS))
    parser.add_argument("--fixtures", type=Path, help="default: tests/fixtures/taint/<c|python>")
    parser.add_argument("--max-depth", type=int, default=4, help="Joern maxCallDepth (default 4)")
    parser.add_argument("--image", default="shield-joern")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--print-script", action="store_true")
    parser.add_argument("--from-output", type=Path, help="parse a saved Joern console output")
    args = parser.parse_args(argv)

    spec = registry.get(args.lang)
    script = build_script(spec, max_call_depth=args.max_depth)
    if args.print_script:
        print(script)
        return 0

    fixtures = args.fixtures or ROOT / "tests" / "fixtures" / "taint" / FIXTURE_DIRS[args.lang]
    if args.from_output:
        text = args.from_output.read_text(encoding="utf-8", errors="replace")
    else:
        text = run_joern(script, fixtures, args.image, args.timeout)
    report = parse_output(text)
    if report.sources is None or report.sinks_found is None:
        print("No @@SRC / @@SNK lines in the output: the script did not run. Output tail:")
        print("\n".join(text.splitlines()[-25:]))
        return 2

    # Rule 3 of the spike: look at the endpoint counts BEFORE reading any flow.
    print(f"sources: {report.sources}   sinks: {report.sinks_found}   flows: {len(report.flows)}")
    rows = evaluate(report, read_expectations(fixtures), args.max_depth)
    print(format_table(rows))
    counts = summarize(rows)
    print("\n" + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    return 1 if counts.get("UNEXPECTED") else 0


if __name__ == "__main__":
    sys.exit(main())
