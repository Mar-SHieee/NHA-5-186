import re
from pathlib import Path

import pytest

from languages import registry
from scripts.taint.run_taint_spike import (
    KNOWN_MISSES,
    evaluate,
    format_table,
    main,
    read_expectations,
    summarize,
)
from shield_core.taint import joern_queries as q
from shield_core.taint.joern_queries import Step, clean_steps, parse_output

CPP = registry.get("cpp")
PYTHON = registry.get("python")


def test_python_definitions_match_the_ones_verified_in_the_spike():
    text = q.source_definition(PYTHON)
    assert text.startswith("def src: Iterator[CfgNode] = cpg.call.code(")
    assert 'cpg.call.code("request\\\\.args\\\\[.*")' in text
    assert "\n" not in text
    sinks = q.sink_definition(PYTHON)
    assert 'cpg.call.name("system").code("os\\\\.system.*").argument(1)' in sinks
    assert 'cpg.call.name("execute").argument(1)' in sinks


def test_cpp_definitions_cover_the_three_source_kinds():
    text = q.source_definition(CPP)
    assert 'cpg.call.name("getenv")' in text  # call
    assert 'cpg.call.name("fgets").argument(1)' in text  # argument (out-parameter)
    assert 'cpg.method.parameter.name("argv")' in text  # parameter
    assert "\n" not in text and "\n" not in q.sink_definition(CPP)


def test_arg_from_sink_filters_on_the_index():
    sink = registry.SinkSpec(name="sprintf", arg_from=3)
    assert q.sink_expression(sink) == (
        'cpg.call.name("sprintf").argument.filter(_.argumentIndex >= 3)'
    )


def test_empty_lists_still_give_valid_scala():
    spec = registry.get("java")  # disabled, empty taint lists
    assert q.source_definition(spec).endswith("= Iterator.empty")
    assert q.sanitizer_pattern(spec) == "(?!)"


def test_scala_string_escapes_backslash_and_quote():
    assert q.scala_string('a\\.b"c') == '"a\\\\.b\\"c"'


def test_script_has_no_raw_control_characters_and_uses_the_right_accessor():
    script = q.build_script(CPP, max_call_depth=8)
    assert all(ord(c) >= 32 or c == "\n" for c in script)
    assert "importCode.c(inputPath)" in script
    assert "maxCallDepth = 8" in script
    assert "importCode.python(inputPath)" in q.build_script(PYTHON)  # not `pythonsrc`


def test_sanitizer_pattern_matches_whole_names_only():
    pattern = re.compile(q.sanitizer_pattern(CPP))
    assert pattern.fullmatch("realpath")
    assert not pattern.fullmatch("realpath_x")
    assert not pattern.fullmatch("strncpy")


# ------------------------------------------------------------ output parsing and verdicts


def sink(file, method, line, call):
    return "\t".join(["@@SINK", file, method, line, call])


def flow(file, method, line, call, san="0", path=(("IDENTIFIER", "6", "c"),)):
    steps = q.PATH_SEP.join(q.STEP_SEP.join(p) for p in path)
    return "\t".join(["@@FLOW", file, method, line, call, san, steps])


def test_parse_output_ignores_joern_noise():
    text = "\n".join(
        [
            "Welcome to Joern",
            "joern> @@SRC\t3",
            "@@SNK\t2",
            sink("a.c", "f", "5", "system(c)"),
            flow("a.c", "f", "5", "system(c)", "1"),
            "val res0: Int = 4",
        ]
    )
    report = parse_output(text)
    assert (report.sources, report.sinks_found) == (3, 2)
    assert report.sinks[0].method == "f"
    assert report.flows[0].sanitizer_present is True


def test_clean_steps_drops_temporaries_and_duplicates():
    steps = [
        Step("CALL", "3", "request.args"),
        Step("IDENTIFIER", "3", "tmp0"),
        Step("IDENTIFIER", "3", "tmp0 = {}"),
        Step("IDENTIFIER", "4", "q"),
        Step("IDENTIFIER", "4", "q"),
    ]
    assert [s.code for s in clean_steps(steps)] == ["request.args", "q"]


def make_fixtures(folder: Path) -> Path:
    files = {
        "c01_getenv_direct.c": "// c01\n// EXPECT: flow\n",
        "c02_constant.c": "// c02\n// EXPECT: no-flow\n",
        "c05_cross_function.c": "// c05\n// EXPECT: flow for both\n",
        "c10_arg_shapes.c": "// Not a flow fixture\n",
        "c21_strncpy.c": "// c21\n// EXPECT: flow   (a bounded copy)\n",
        "c22_realpath.c": "// c22\n// EXPECT: flow for both\n",
        "c24_copy_functions.c": "// c24\n// EXPECT: flow for all seven\n",
    }
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def test_read_expectations(tmp_path):
    got = read_expectations(make_fixtures(tmp_path))
    assert got["c01_getenv_direct.c"] == "flow"
    assert got["c02_constant.c"] == "no-flow"
    assert got["c05_cross_function.c"] == "flow"
    assert "c10_arg_shapes.c" not in got


def observed_output() -> str:
    """The sinks and flows OBSERVED in the C spike for the fixtures above (Joern 4.0.647)."""
    return "\n".join(
        [
            "@@SRC\t9",
            "@@SNK\t9",
            sink("c01_getenv_direct.c", "f_c01", "5", "system(c)"),
            flow("c01_getenv_direct.c", "f_c01", "5", "system(c)"),
            sink("c02_constant.c", "f_c02", "5", 'system("ls")'),
            sink("c05_cross_function.c", "run", "3", "system(c)"),
            flow("c05_cross_function.c", "run", "3", "system(c)"),
            sink("c05_cross_function.c", "f_c05a", "6", "system(read_cmd())"),
            flow("c05_cross_function.c", "f_c05a", "6", "system(read_cmd())"),
            sink("c10_arg_shapes.c", "f_c10", "9", "strcpy(a, src)"),
            sink("c21_strncpy.c", "f_c21", "8", "system(buf)"),
            sink("c22_realpath.c", "f_c22a", "8", 'fopen(resolved, "r")'),
            flow("c22_realpath.c", "f_c22a", "8", 'fopen(resolved, "r")', "1"),
            sink("c24_copy_functions.c", "f_c24e", "9", "memcpy(buf, c, 16)"),
            sink("c24_copy_functions.c", "f_c24e", "9", "system(buf)"),
            flow("c24_copy_functions.c", "f_c24e", "9", "system(buf)"),
        ]
    )


def test_verdicts_follow_the_observed_spike_results(tmp_path):
    rows = evaluate(parse_output(observed_output()), read_expectations(make_fixtures(tmp_path)))
    verdicts = {(r.file, r.method, r.call): r.verdict for r in rows}
    assert verdicts[("c01_getenv_direct.c", "f_c01", "system(c)")] == "OK"
    assert verdicts[("c02_constant.c", "f_c02", 'system("ls")')] == "OK"  # negative control
    assert verdicts[("c05_cross_function.c", "run", "system(c)")] == "OK"
    assert verdicts[("c10_arg_shapes.c", "f_c10", "strcpy(a, src)")] == "SKIP"
    assert verdicts[("c21_strncpy.c", "f_c21", "system(buf)")] == "KNOWN-MISS"
    assert verdicts[("c24_copy_functions.c", "f_c24e", "memcpy(buf, c, 16)")] == "OK"
    assert "UNEXPECTED" not in summarize(rows)


def test_the_sanitizer_flag_is_checked_in_both_directions(tmp_path):
    fixtures = make_fixtures(tmp_path)
    rows = evaluate(parse_output(observed_output()), read_expectations(fixtures))
    c22 = [r for r in rows if r.method == "f_c22a"][0]
    assert (c22.verdict, c22.sanitized) == ("OK", True)
    unset = observed_output().replace(
        flow("c22_realpath.c", "f_c22a", "8", 'fopen(resolved, "r")', "1"),
        flow("c22_realpath.c", "f_c22a", "8", 'fopen(resolved, "r")', "0"),
    )
    rows = evaluate(parse_output(unset), read_expectations(fixtures))
    assert [r.verdict for r in rows if r.method == "f_c22a"] == ["UNEXPECTED"]
    spurious = observed_output().replace(
        flow("c01_getenv_direct.c", "f_c01", "5", "system(c)"),
        flow("c01_getenv_direct.c", "f_c01", "5", "system(c)", "1"),
    )
    rows = evaluate(parse_output(spurious), read_expectations(fixtures))
    assert [r.verdict for r in rows if r.method == "f_c01"] == ["UNEXPECTED"]


def python_fixtures(folder: Path) -> Path:
    files = {
        "py07b_container_precision.py": "# py07b\n# EXPECT: no-flow\n",
        "py11_attribute.py": "# py11\n# EXPECT: flow\n",
        "py12_depth.py": "# py12\n# EXPECT: flow for both\n",
        "py14_cast_sanitizer.py": "# py14\n# EXPECT: flow\n",
    }
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def python_output(include_deep: bool) -> str:
    lines = [
        "@@SRC\t4",
        "@@SNK\t4",
        sink("py07b_container_precision.py", "handler_py07b", "4", 'cur.execute(d["j"])'),
        flow("py07b_container_precision.py", "handler_py07b", "4", 'cur.execute(d["j"])'),
        sink("py11_attribute.py", "query", "6", "cur.execute(self.uid)"),
        sink("py12_depth.py", "handler_py12b", "9", "cur.execute(f1(x))"),
        sink("py14_cast_sanitizer.py", "handler_py14", "5", "cur.execute(str(uid))"),
        flow("py14_cast_sanitizer.py", "handler_py14", "5", "cur.execute(str(uid))", "1"),
    ]
    if include_deep:
        lines.append(flow("py12_depth.py", "handler_py12b", "9", "cur.execute(f1(x))"))
    return "\n".join(lines)


def test_python_known_false_positive_depth_miss_and_sanitizer(tmp_path):
    fixtures = read_expectations(python_fixtures(tmp_path))
    rows = evaluate(parse_output(python_output(False)), fixtures)
    verdicts = {r.method: r.verdict for r in rows}
    assert verdicts == {
        "handler_py07b": "KNOWN-FP",
        "query": "KNOWN-MISS",
        "handler_py12b": "KNOWN-MISS",  # depth miss, default depth
        "handler_py14": "OK",  # int(...) flagged as a sanitizer
    }
    assert "UNEXPECTED" not in summarize(rows)


def test_depth_misses_apply_only_at_the_default_depth(tmp_path):
    fixtures = read_expectations(python_fixtures(tmp_path))
    rows = evaluate(parse_output(python_output(True)), fixtures, max_depth=8)
    assert [r.verdict for r in rows if r.method == "handler_py12b"] == ["OK"]
    # the same flow at the default depth would mean the documented miss is gone
    rows = evaluate(parse_output(python_output(True)), fixtures, max_depth=4)
    assert [r.verdict for r in rows if r.method == "handler_py12b"] == ["NOW-OK"]


def test_a_vanished_false_positive_is_flagged(tmp_path):
    fixtures = read_expectations(python_fixtures(tmp_path))
    quiet = python_output(False).replace(
        flow("py07b_container_precision.py", "handler_py07b", "4", 'cur.execute(d["j"])'), ""
    )
    rows = evaluate(parse_output(quiet), fixtures)
    assert [r.verdict for r in rows if r.method == "handler_py07b"] == ["NOW-OK"]


def test_an_undocumented_miss_is_unexpected_and_a_fixed_one_is_flagged(tmp_path):
    fixtures = make_fixtures(tmp_path)
    missing = observed_output().replace(flow("c01_getenv_direct.c", "f_c01", "5", "system(c)"), "")
    assert (
        summarize(evaluate(parse_output(missing), read_expectations(fixtures)))["UNEXPECTED"] == 1
    )
    fixed = observed_output() + "\n" + flow("c21_strncpy.c", "f_c21", "8", "system(buf)")
    rows = evaluate(parse_output(fixed), read_expectations(fixtures))
    assert [r.verdict for r in rows if r.method == "f_c21"] == ["NOW-OK"]


def test_a_false_positive_on_a_negative_control_is_unexpected(tmp_path):
    extra = observed_output() + "\n" + flow("c02_constant.c", "f_c02", "5", 'system("ls")')
    rows = evaluate(parse_output(extra), read_expectations(make_fixtures(tmp_path)))
    assert summarize(rows)["UNEXPECTED"] == 1


def test_table_is_markdown(tmp_path):
    rows = evaluate(parse_output(observed_output()), read_expectations(make_fixtures(tmp_path)))
    assert format_table(rows).splitlines()[0].startswith("| file |")


def test_known_tables_name_real_fixture_files():
    from scripts.taint.run_taint_spike import KNOWN_DEPTH_MISSES, KNOWN_FALSE_POSITIVES

    pattern = r"(c|py)\d\d[a-z]?_[a-z_]+\.(c|cpp|py)"
    for table in (KNOWN_MISSES, KNOWN_DEPTH_MISSES, KNOWN_FALSE_POSITIVES):
        for file, method in table:
            assert re.fullmatch(pattern, file), file
            assert method


def test_cli_prints_the_script_and_reports_a_missing_run(tmp_path, capsys):
    assert main(["--lang", "cpp", "--print-script"]) == 0
    assert "@main def exec" in capsys.readouterr().out
    empty = tmp_path / "out.txt"
    empty.write_text("nothing here\n", encoding="utf-8")
    assert main(["--lang", "cpp", "--from-output", str(empty), "--fixtures", str(tmp_path)]) == 2


@pytest.mark.parametrize("lang", ["cpp", "python"])
def test_script_mentions_every_sanitizer_and_endpoint(lang):
    script = q.build_script(registry.get(lang))
    assert "def src:" in script and "def snk:" in script and "val sanitizers" in script
