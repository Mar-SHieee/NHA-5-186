"""Torch-free filter behavior, including published Joern golden counts."""

import pytest

from shield_core.extraction.graph_extractor import GraphEdge, GraphNode
from shield_core.graph_dataset.filtering import filter_graph
from shield_core.graph_dataset.schema import ConverterConfig

GOLDEN = {
    "get_user_py": (96, 499, 48, 176, [47, 38, 64, 0, 27, 0], (48, 176)),
    "branch_py": (104, 540, 54, 194, [53, 40, 70, 0, 26, 5], (54, 194)),
    "calls_py": (115, 580, 60, 207, [59, 43, 76, 1, 28, 0], (60, 207)),
    "overflow_c": (66, 246, 25, 69, [22, 13, 27, 1, 6, 0], (20, 59)),
    "vec_cpp": (66, 246, 25, 69, [22, 13, 27, 1, 6, 0], (20, 59)),
}


@pytest.mark.parametrize("name", GOLDEN)
def test_fixture_golden_counts(name, load_graph):
    raw_n, raw_e, kept_n, kept_e, edge_counts, rule_b = GOLDEN[name]
    graph = load_graph(name)
    assert (len(graph.nodes), len(graph.edges)) == (raw_n, raw_e)
    result = filter_graph(graph, ConverterConfig())
    assert result.reason == "ok"
    assert (result.diagnostics.n_nodes, result.diagnostics.n_edges) == (kept_n, kept_e)
    assert list(result.diagnostics.edge_counts.values()) == edge_counts
    result_b = filter_graph(graph, ConverterConfig(stub_rule="B"))
    assert (result_b.diagnostics.n_nodes, result_b.diagnostics.n_edges) == rule_b


def test_operator_children_removed_and_rows_sorted(make_graph):
    graph = make_graph(
        [
            GraphNode(3, "IDENTIFIER"),
            GraphNode(2, "CALL"),
            GraphNode(1, "METHOD", name="<operator>.addition"),
        ],
        [GraphEdge(1, 2, "AST"), GraphEdge(1, 3, "AST")],
    )
    result = filter_graph(graph, ConverterConfig())
    assert result.reason == "empty_after_filter"


def test_rule_b_drops_line_less_method_but_rule_a_keeps(make_graph):
    graph = make_graph(
        [GraphNode(1, "METHOD", name="external"), GraphNode(2, "CALL")], [GraphEdge(2, 1, "CALL")]
    )
    assert filter_graph(graph, ConverterConfig()).diagnostics.n_nodes == 2
    assert filter_graph(graph, ConverterConfig(stub_rule="B")).diagnostics.n_nodes == 1


def test_cap_skips_instead_of_truncating(tiny_graph):
    result = filter_graph(tiny_graph, ConverterConfig(max_nodes=1))
    assert result.reason == "over_node_cap"
    assert result.graph is None
    assert result.diagnostics.n_nodes == 2


def test_cap_boundary_unwanted_types_edge_types_and_duplicate_edges(make_graph):
    graph = make_graph(
        [
            GraphNode(3, "IDENTIFIER"),
            GraphNode(4, "UNKNOWN"),
            GraphNode(2, "CALL"),
            GraphNode(1, "METHOD", name="f", line=1),
        ],
        [
            GraphEdge(1, 2, "AST"),
            GraphEdge(1, 2, "AST"),
            GraphEdge(2, 3, "CFG"),
            GraphEdge(4, 1, "CFG"),
            GraphEdge(1, 3, "CDG"),
        ],
    )
    result = filter_graph(graph, ConverterConfig(max_nodes=3, edge_types=("AST", "CFG")))
    assert result.reason == "ok"
    assert [node.id for node in result.graph.nodes] == [1, 2, 3]
    assert result.graph.edges == [(0, 1, 0), (0, 1, 0), (1, 2, 1)]
    assert result.diagnostics.n_unknown == 1
    assert filter_graph(graph, ConverterConfig(max_nodes=2)).reason == "over_node_cap"


def test_unusable_is_diagnostic_unless_requested_for_dropping(make_graph):
    graph = make_graph([GraphNode(1, "METHOD", name="<module>"), GraphNode(2, "CALL")])
    assert filter_graph(graph, ConverterConfig()).reason == "ok"
    dropped = filter_graph(graph, ConverterConfig(drop_unusable=True))
    assert dropped.reason == "unusable"
    assert dropped.graph is None


def test_filtering_does_not_import_torch():
    import subprocess
    import sys

    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import shield_core.graph_dataset.filtering; "
            "assert 'torch' not in sys.modules",
        ],
        check=True,
    )
