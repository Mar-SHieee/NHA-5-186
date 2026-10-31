"""Compatibility wrapper: convert a GraphML export using the maintained converter."""

import argparse

import torch

from shield_core.extraction.graph_extractor import GRAPH_SCHEMA_VERSION, CodeGraph
from shield_core.extraction.joern_extractor import DEFAULT_JOERN_VERSION, parse_graphml
from shield_core.graph_dataset.filtering import filter_graph
from shield_core.graph_dataset.schema import EDGE_TYPES, ConverterConfig
from shield_core.graph_dataset.to_pyg import to_data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graphml")
    args = parser.parse_args()
    nodes, edges = parse_graphml(args.graphml)
    graph = CodeGraph("python", "joern", DEFAULT_JOERN_VERSION, GRAPH_SCHEMA_VERSION, nodes, edges)
    filtered = filter_graph(graph, ConverterConfig())
    if filtered.graph is None:
        raise SystemExit(filtered.reason)
    data = to_data(filtered.graph)
    summary = (
        f"Data(x=[{data.num_nodes}, 15], edge_index=[2, {data.num_edges}], "
        f"edge_type=[{data.num_edges}])"
    )
    print(summary)
    counts = torch.bincount(data.edge_type, minlength=len(EDGE_TYPES)).tolist()
    print("edges per type:", dict(zip(EDGE_TYPES, counts, strict=True)))


if __name__ == "__main__":
    main()
