"""Unit tests for the pure graph-quality triage rules; no Docker is needed."""

import pytest

from scripts.spikes.joern.triage_core import (
    DotStats,
    audit_flags,
    classify,
    flow_expectation,
    graph_metrics,
    is_usable,
    label_type,
    language_verdict,
    parse_dot,
    preserve_block,
    real_unknown_count,
    stub_rule_impact,
    substring_unknown_count,
    wilson_interval,
)
from shield_core.extraction.graph_extractor import CodeGraph, GraphEdge, GraphNode


def _graph(nodes, edges=(), language="python"):
    return CodeGraph(language, "fixture", "1", "1", nodes, list(edges))


def test_parse_dot_counts_nodes_edges_and_unescapes_labels():
    stats = parse_dot(
        'digraph "f" {\n'
        '  "1" [label = <METHOD, 1<BR/>f &amp; g> ]\n'
        '  "2" [label = <UNKNOWN, 2<BR/>unknown_x> ]\n'
        '  "3" [label = <CALL, 3<BR/>h()> ]\n'
        '  "1" -> "2"\n'
        '  "2" -> "3" [ label = "CFG"]\n'
        "}\n"
    )

    assert stats.nodes == {
        "1": "METHOD, 1<BR/>f & g",
        "2": "UNKNOWN, 2<BR/>unknown_x",
        "3": "CALL, 3<BR/>h()",
    }
    assert stats.edges == {("1", "2"), ("2", "3")}


def test_parse_dot_handles_an_empty_dot_view():
    stats = parse_dot('digraph "f" {\nnode [shape="rect"];\n}\n')
    assert stats.nodes == {}
    assert stats.edges == set()


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("&lt;operator&gt;.assignment, 3<BR/>x = y", "<operator>.assignment"),
        ("METHOD, 1<BR/>f, detail", "METHOD"),
        ("UNKNOWN, 2<BR/>some code", "UNKNOWN"),
        ("assertEqual, 11<BR/>self.assertEqual(a, b)", "assertEqual"),
    ],
)
def test_label_type_returns_first_label_token(label, expected):
    assert label_type(label) == expected


@pytest.mark.parametrize(
    ("cfg", "ddg", "cpg_ok", "source_ok", "expected"),
    [
        (
            DotStats(),
            DotStats(),
            True,
            False,
            ["MISSING_SOURCE", "NO_CFG_DOT_FILES", "NO_DDG_DOT_FILES"],
        ),
        (
            DotStats(),
            DotStats(),
            False,
            True,
            ["MISSING_OR_EMPTY_CPG", "NO_CFG_DOT_FILES", "NO_DDG_DOT_FILES"],
        ),
        (
            DotStats(dot_files=1),
            DotStats(dot_files=1),
            True,
            True,
            ["CFG_HAS_NO_NODES", "DDG_HAS_NO_NODES"],
        ),
        (
            DotStats(nodes={"1": "METHOD, 1<BR/>f"}, dot_files=1),
            DotStats(nodes={"2": "METHOD, 1<BR/>f"}, dot_files=1),
            True,
            True,
            ["CFG_HAS_NO_EDGES", "DDG_HAS_NO_EDGES"],
        ),
        (
            DotStats(nodes={"1": "CALL, 1<BR/>f()"}, edges={("1", "2")}, dot_files=1),
            DotStats(),
            True,
            True,
            ["CFG_NO_METHOD_NODE", "NO_DDG_DOT_FILES"],
        ),
        (
            DotStats(
                nodes={"1": "METHOD, 1<BR/>f", "2": "UNKNOWN, 2<BR/>ErrorStatement"},
                edges={("1", "2")},
                dot_files=1,
            ),
            DotStats(nodes={"2": "METHOD, 1<BR/>f"}, edges={("2", "3")}, dot_files=1),
            True,
            True,
            ["CFG_UNKNOWN_NODES"],
        ),
    ],
)
def test_audit_flags_reproduces_each_flag_rule(cfg, ddg, cpg_ok, source_ok, expected):
    assert audit_flags(cfg, ddg, cpg_ok=cpg_ok, source_ok=source_ok) == expected


def test_audit_flags_clean_sample_has_no_flags():
    cfg = DotStats(nodes={"1": "METHOD, 1<BR/>f"}, edges={("1", "2")}, dot_files=1)
    ddg = DotStats(nodes={"1": "METHOD, 1<BR/>f"}, edges={("1", "2")}, dot_files=1)
    assert audit_flags(cfg, ddg, cpg_ok=True, source_ok=True) == []


def test_audit_flags_match_recorded_c01_audit_row():
    # The real c_01 CSV row has both audit flags: an UNKNOWN CFG label and an empty DDG view.
    cfg = DotStats(
        nodes={"1": "UNKNOWN, 1<BR/>ErrorStatement", "2": "METHOD, 1<BR/><global>"},
        edges={("1", "2")},
        dot_files=2,
    )
    ddg = DotStats(dot_files=2)
    assert audit_flags(cfg, ddg, cpg_ok=True, source_ok=True) == [
        "CFG_UNKNOWN_NODES",
        "DDG_HAS_NO_NODES",
    ]


def test_real_unknown_and_substring_unknown_are_distinct():
    labels = ["UNKNOWN, 1<BR/>ParseException", "IDENTIFIER, 2<BR/>unknown_x"]
    assert real_unknown_count(labels) == 1
    assert substring_unknown_count(labels) == 2


def test_graph_metrics_counts_edges_unknowns_and_line_less_methods():
    graph = _graph(
        [
            GraphNode(1, "METHOD", "<empty>", "f", 1),
            GraphNode(2, "METHOD", "<empty>", "external", None),
            GraphNode(3, "UNKNOWN", "bad syntax", "", 2),
        ],
        [GraphEdge(1, 2, "CALL"), GraphEdge(1, 3, "CFG"), GraphEdge(3, 2, "REACHING_DEF")],
    )

    metrics = graph_metrics(graph)
    assert metrics.n_nodes == 3
    assert metrics.n_edges == 3
    assert metrics.edge_counts == {"CALL": 1, "CFG": 1, "REACHING_DEF": 1}
    assert metrics.n_unknown_nodes == 1
    assert metrics.unknown_share == pytest.approx(1 / 3)
    assert metrics.methods == [("f", 1), ("external", None)]
    assert metrics.n_real_methods == 1
    assert metrics.n_lineless_methods == 1
    assert metrics.has_reaching_def is True


def test_flow_expectation_python_uses_parameters_and_prior_assignments():
    count, method = flow_expectation("python", "def f(x):\n    y = x\n    return y\n")
    assert count == 2
    assert method == "ast"


def test_flow_expectation_constant_return_has_no_expected_flow():
    assert flow_expectation("python", "def f():\n    return 1\n") == (0, "ast")


def test_flow_expectation_syntax_error_falls_back_without_raising():
    count, method = flow_expectation("python", "def f(:\n    return x\n")
    assert count >= 0
    assert method.startswith("regex")


def test_flow_expectation_c_uses_documented_regex_heuristic():
    count, method = flow_expectation("cpp", "int f(int x) { int y = x; return y; }")
    assert count >= 1
    assert method == "regex"


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"extraction_failed": True}, "EXTRACTION_FAILURE"),
        ({"n_real_methods": 0, "input_fragment": True}, "INPUT_FRAGMENT"),
        ({"expected_flow": 2, "reaching_def": 0}, "PARSER_GAP"),
        ({"expected_flow": 0, "unknown_share": 0.06}, "PARSER_GAP"),
        ({"ddg_dot_edges": 0, "reaching_def": 1, "expected_flow": 1}, "DOT_VIEW_ONLY"),
        ({"expected_flow": 0, "unknown_share": 0}, "EXPECTED_NO_FLOW"),
        (
            {
                "flagged": True,
                "real_methods": 1,
                "cfg_edges": 1,
                "expected_flow": 1,
                "reaching_def": 1,
                "ddg_dot_edges": 1,
                "unknown_share": 0,
            },
            "AUDIT_ARTIFACT",
        ),
        (
            {"expected_flow": 1, "reaching_def": 1, "ddg_dot_edges": 1, "unknown_share": 0},
            "OTHER",
        ),
    ],
)
def test_classify_returns_expected_primary_cause(row, expected):
    assert classify(row)[0] == expected


def test_classify_prefers_parser_gap_when_flow_and_unknowns_both_fail():
    row = {"expected_flow": 1, "reaching_def": 0, "unknown_share": 0.2}
    assert classify(row)[0] == "PARSER_GAP"


@pytest.mark.parametrize(
    ("unknown_share", "expected_flow", "reaching_def", "expected"),
    [
        (0.05, 1, 1, True),
        (0.051, 0, 0, False),
        (0.0, 0, 0, True),
        (0.0, 1, 0, False),
    ],
)
def test_is_usable_applies_u1_to_u4(unknown_share, expected_flow, reaching_def, expected):
    row = {
        "real_methods": 1,
        "cfg_edges": 1,
        "expected_flow": expected_flow,
        "reaching_def": reaching_def,
        "unknown_share": unknown_share,
    }
    assert is_usable(row) is expected


def test_wilson_interval_matches_hand_calculation_and_edges():
    assert wilson_interval(17, 20) == pytest.approx((0.6396, 0.9476), abs=0.0001)
    assert wilson_interval(0, 20)[0] == 0
    assert wilson_interval(20, 20)[1] == 1
    with pytest.raises(ValueError):
        wilson_interval(1, 0)


@pytest.mark.parametrize(
    ("k", "expected"),
    [(17, "GO"), (16, "GO-WITH-LIMITS"), (14, "GO-WITH-LIMITS"), (13, "NO-GO")],
)
def test_language_verdict_thresholds(k, expected):
    assert language_verdict(k, 20) == expected


def test_stub_rule_impact_reports_removed_stub_edges_and_components():
    graph = _graph(
        [
            GraphNode(1, "METHOD", "f()", "f", 1),
            GraphNode(2, "METHOD", "<empty>", "strcpy", None),
            GraphNode(3, "IDENTIFIER", "src", "src", 1),
        ],
        [GraphEdge(1, 2, "CALL"), GraphEdge(1, 3, "CFG")],
    )

    impact = stub_rule_impact(graph)
    assert impact.dropped_nodes == 1
    assert impact.dropped_edges_by_type == {"CALL": 1}
    assert impact.kept_edge_loss == 0
    assert impact.components_a == impact.components_b == 1
    assert impact.dropped_have_text is False


def test_stub_rule_impact_reports_when_stub_bridges_kept_components():
    graph = _graph(
        [
            GraphNode(1, "IDENTIFIER", "a", "a", 1),
            GraphNode(2, "METHOD", "<empty>", "external", None),
            GraphNode(3, "IDENTIFIER", "b", "b", 1),
        ],
        [GraphEdge(1, 2, "REACHING_DEF"), GraphEdge(2, 3, "CFG")],
    )
    impact = stub_rule_impact(graph)
    assert impact.kept_edge_loss == 2
    assert impact.components_b > impact.components_a


def test_stub_rule_impact_marks_dropped_source_text():
    graph = _graph([GraphNode(1, "METHOD", "external()", "external", None)])
    assert stub_rule_impact(graph).dropped_have_text is True


def test_preserve_block_appends_old_block_when_new_report_has_none():
    old = "report\n<!-- TRIAGE:BEGIN -->\nold\n<!-- TRIAGE:END -->\n"
    new = "fresh report\n"
    assert preserve_block(old, new, "<!-- TRIAGE:BEGIN -->", "<!-- TRIAGE:END -->").endswith(
        "<!-- TRIAGE:BEGIN -->\nold\n<!-- TRIAGE:END -->\n"
    )


def test_preserve_block_keeps_new_block_when_present():
    old = "<!-- TRIAGE:BEGIN -->\nold\n<!-- TRIAGE:END -->"
    new = "<!-- TRIAGE:BEGIN -->\nnew\n<!-- TRIAGE:END -->"
    assert preserve_block(old, new, "<!-- TRIAGE:BEGIN -->", "<!-- TRIAGE:END -->") == new


def test_preserve_block_leaves_unmarked_text_unchanged():
    new = "plain report\n"
    assert preserve_block("old report", new, "BEGIN", "END") == new
