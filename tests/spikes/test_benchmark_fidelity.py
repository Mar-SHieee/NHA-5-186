from scripts.spikes.joern.benchmark_fidelity import (
    _graphml,
    _verdict,
    attribute_nodes,
    compare_graphs,
    signal_diagnostics,
)
from shield_core.extraction.graph_extractor import GraphEdge, GraphNode

TINY_GRAPHML = """<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="label" for="node" attr.name="labelV" attr.type="string"/>
  <key id="filename" for="node" attr.name="FILENAME" attr.type="string"/>
  <key id="name" for="node" attr.name="NAME" attr.type="string"/>
  <key id="edge" for="edge" attr.name="labelE" attr.type="string"/>
  <graph edgedefault="directed">
    <node id="1">
      <data key="label">METHOD</data><data key="filename">a.py</data>
      <data key="name">a</data>
    </node>
    <node id="2"><data key="label">CALL</data><data key="filename">a.py</data></node>
    <node id="3">
      <data key="label">METHOD</data><data key="filename">b.py</data>
      <data key="name">b</data>
    </node>
    <node id="4">
      <data key="label">METHOD</data><data key="filename">&lt;empty&gt;</data>
      <data key="name">external</data>
    </node>
    <edge source="1" target="2"><data key="edge">AST</data></edge>
    <edge source="1" target="3"><data key="edge">CALL</data></edge>
    <edge source="3" target="4"><data key="edge">CALL</data></edge>
  </graph>
</graphml>"""


def test_tiny_graphml_attributes_filename_nodes_and_counts_cross_file_calls():
    nodes, edges = _graphml(TINY_GRAPHML)
    keys = {"a.py", "b.py"}
    owners = attribute_nodes(nodes, edges)
    assert owners == {"1": "a.py", "2": "a.py", "3": "b.py"}
    diagnostics = signal_diagnostics(nodes, edges, keys)
    assert diagnostics["METHOD.FILENAME"]["files"] == ["a.py", "b.py"]

    singles = {
        "a.py": ([GraphNode(1, "METHOD"), GraphNode(2, "CALL")], [GraphEdge(1, 2, "AST")]),
        "b.py": ([GraphNode(3, "METHOD")], []),
    }
    comparison = compare_graphs(nodes, edges, owners, singles, keys)
    assert comparison["cross_file_call_edges"] == 1
    assert comparison["unattributable_method_nodes"] == 1
    assert comparison["per_file"]["a.py"]["node_types_match"]
    assert comparison["per_file"]["a.py"]["edge_types_match"]
    assert _verdict(comparison)[0] == "not usable"


def test_empty_filename_is_left_unattributable():
    nodes, edges = _graphml(TINY_GRAPHML)
    assert "4" not in attribute_nodes(nodes, edges, {"a.py", "b.py"})
