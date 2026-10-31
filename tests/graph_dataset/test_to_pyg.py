"""Optional PyG tensor contract tests."""

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("torch_geometric")

from shield_core.graph_dataset.filtering import filter_graph  # noqa: E402
from shield_core.graph_dataset.schema import ConverterConfig  # noqa: E402
from shield_core.graph_dataset.to_pyg import to_data  # noqa: E402


def test_golden_tensors(load_graph):
    result = filter_graph(load_graph("get_user_py"), ConverterConfig())
    data = to_data(result.graph, y=1)
    assert tuple(data.x.shape) == (48, 15)
    assert tuple(data.edge_index.shape) == (2, 176)
    assert torch.all(data.x[:, :12].sum(1) == 1)
    assert torch.all(data.x[:, 12:] == 0)
    assert data.validate()


def test_empty_edges_have_coo_shape(make_graph):
    graph = make_graph(
        [
            __import__("shield_core.extraction.graph_extractor", fromlist=["GraphNode"]).GraphNode(
                1, "METHOD"
            )
        ]
    )
    data = to_data(filter_graph(graph, ConverterConfig()).graph)
    assert tuple(data.edge_index.shape) == (2, 0)
