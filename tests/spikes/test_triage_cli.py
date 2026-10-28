"""CLI glue tests use fake graphs and directories; they never start Docker."""

import csv
import json

import pytest

from scripts.spikes.joern import triage_joern_spike as triage_cli
from scripts.spikes.joern.benchmark_core import Sample
from shield_core.extraction.graph_extractor import CodeGraph, GraphEdge, GraphNode


def test_analyze_writes_fixed_columns_and_card_for_flagged_sample(tmp_path, monkeypatch):
    sample = Sample(
        "python_spike_001",
        "python",
        ".py",
        "def f(x):\n    return x\n",
        "spike",
        "fixture",
        0,
    )
    sample_dir = tmp_path / "spike" / "python_01"
    (sample_dir / "cfg_export").mkdir(parents=True)
    (sample_dir / "ddg_export").mkdir()
    (sample_dir / "sample.py").write_text(sample.code, encoding="utf-8")
    (sample_dir / "cpg.bin").write_bytes(b"cpg")
    (sample_dir / "cfg_export" / "0-cfg.dot").write_text(
        'digraph "f" {\n'
        '"1" [label = <METHOD, 1<BR/>f> ]\n'
        '"2" [label = <UNKNOWN, 1<BR/>error> ]\n'
        '"1" -> "2"\n}\n',
        encoding="utf-8",
    )
    (sample_dir / "ddg_export" / "0-ddg.dot").write_text(
        'digraph "f" {\nnode [shape="rect"];\n}\n', encoding="utf-8"
    )
    graph = CodeGraph(
        "python",
        "fixture",
        "1",
        "1",
        [
            GraphNode(1, "METHOD", "def f(x): return x", "f", 1),
            GraphNode(2, "UNKNOWN", "error", "", 1),
            GraphNode(3, "IDENTIFIER", "x", "x", 1),
        ],
        [GraphEdge(1, 3, "CFG"), GraphEdge(1, 3, "REACHING_DEF")],
    )

    class FakeCache:
        def get(self, key):
            return graph

    monkeypatch.setattr(triage_cli, "load_spike_samples", lambda: [sample])
    monkeypatch.setattr(triage_cli, "GraphCache", lambda root: FakeCache())

    summary = triage_cli.analyze_samples(
        spike_root=tmp_path / "spike",
        cache_root=tmp_path / "cache",
        output_dir=tmp_path / "out",
    )

    with (tmp_path / "out" / "triage.csv").open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        row = next(reader)
        assert reader.fieldnames == triage_cli.TRIAGE_COLUMNS
    assert row["sample_id"] == "python_spike_001"
    assert row["flagged"] == "True"
    assert (tmp_path / "out" / "cards" / "python_spike_001.md").is_file()
    assert summary["languages"]["python"]["samples"] == 1
    assert json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8")) == summary
    report_text = triage_cli.report(
        triage_csv=tmp_path / "out" / "triage.csv",
        summary_json=tmp_path / "out" / "summary.json",
        review_csv=tmp_path / "review.csv",
        output_path=tmp_path / "report.md",
    )
    assert "## Per-sample results" in report_text
    assert "python_spike_001" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_main_help_lists_three_subcommands():
    with pytest.raises(SystemExit) as exc:
        triage_cli.main(["--help"])
    assert exc.value.code == 0


def test_scale_sample_selection_excludes_spike_hashes_and_filters_c(monkeypatch):
    original = Sample("c_spike_001", "c", ".c", "int f() { return 1; }", "spike", "bigvul", 0)
    scale_c = Sample("c_scale_001", "c", ".c", "int g() { return 2; }", "scale", "bigvul", 1)
    scale_cpp = Sample(
        "cpp_scale_001", "cpp", ".cpp", "int h() { return 3; }", "scale", "megavul", 1
    )
    observed = {}

    monkeypatch.setattr(triage_cli, "load_spike_samples", lambda: [original])

    def fake_draw(*, n_per_group, seed, exclude_sha):
        observed.update(n=n_per_group, seed=seed, exclude_sha=exclude_sha)
        return [scale_c, scale_cpp]

    monkeypatch.setattr(triage_cli, "draw_scale_samples", fake_draw)
    assert triage_cli._samples_for_set("scale", "c", 100, 43) == [scale_c]
    assert observed == {"n": 100, "seed": 43, "exclude_sha": {original.sha256}}


def test_c_scale_selection_uses_language_filtered_sampler(monkeypatch):
    original = Sample("c_spike_001", "c", ".c", "int f() { return 1; }", "spike", "bigvul", 0)
    c_sample = Sample("c_scale_001", "c", ".c", "int g() { return 2; }", "scale", "cvefixes_cpp", 7)
    observed = {}

    monkeypatch.setattr(triage_cli, "load_spike_samples", lambda: [original])

    def fake_draw(n, seed, exclude_sha):
        observed.update(n=n, seed=seed, exclude_sha=exclude_sha)
        return [c_sample]

    monkeypatch.setattr(triage_cli, "draw_c_scale_samples", fake_draw)
    assert triage_cli._samples_for_set("c-scale", "c", 100, 43) == [c_sample]
    assert observed == {"n": 100, "seed": 43, "exclude_sha": {original.sha256}}


def test_python_context_wrap_only_repairs_graphs_without_a_real_method():
    sample = Sample(
        "python_scale_001",
        "python",
        ".py",
        "    def f(self, x):\n        return x\n",
        "scale",
        "cvefixes_python",
        1,
    )
    wrapper_only_graph = CodeGraph(
        "python",
        "fixture",
        "1",
        "1",
        [GraphNode(1, "METHOD", "module", "<module>", 1)],
        [],
    )
    real_method_graph = CodeGraph(
        "python",
        "fixture",
        "1",
        "1",
        [GraphNode(1, "METHOD", "def f(self, x): return x", "f", 1)],
        [],
    )

    repaired = triage_cli._wrap_python_sample_if_method_missing(sample, wrapper_only_graph)
    unchanged = triage_cli._wrap_python_sample_if_method_missing(sample, real_method_graph)

    assert repaired.code.startswith("class __ShieldSnippet__:\n")
    assert "synthetic-class-wrapper" in repaired.source
    assert unchanged is sample
    assert triage_cli._output_dir("scale", "python", True).name == "python_scale_wrapped"


def test_scale_analysis_does_not_call_missing_ddg_view_dot_view_only(tmp_path, monkeypatch):
    sample = Sample(
        "c_scale_001",
        "c",
        ".c",
        "int f(int x) { int y = x; return y; }",
        "scale",
        "bigvul",
        1,
    )
    graph = CodeGraph(
        "cpp",
        "fixture",
        "1",
        "1",
        [GraphNode(1, "METHOD", "f", "f", 1), GraphNode(2, "IDENTIFIER", "x", "x", 1)],
        [GraphEdge(1, 2, "CFG"), GraphEdge(1, 2, "REACHING_DEF")],
    )

    class FakeCache:
        def get(self, key):
            return graph

    monkeypatch.setattr(triage_cli, "_samples_for_set", lambda *args, **kwargs: [sample])
    monkeypatch.setattr(triage_cli, "GraphCache", lambda root: FakeCache())
    stale_cards = tmp_path / "c_scale" / "cards"
    stale_cards.mkdir(parents=True)
    (stale_cards / "stale.md").write_text("old card", encoding="utf-8")
    summary = triage_cli.analyze_samples(
        spike_root=tmp_path / "unused",
        cache_root=tmp_path / "cache",
        output_dir=tmp_path / "c_scale",
        sample_set="scale",
        group="c",
        n=100,
        seed=43,
    )
    with (tmp_path / "c_scale" / "triage.csv").open(encoding="utf-8", newline="") as f:
        row = next(csv.DictReader(f))
    assert row["auto_cause"] == ""
    assert row["usable"] == "True"
    assert not (tmp_path / "c_scale" / "cards" / "c_scale_001.md").exists()
    assert not (tmp_path / "c_scale" / "cards" / "stale.md").exists()
    assert summary["languages"]["c"]["usable"] == 1
