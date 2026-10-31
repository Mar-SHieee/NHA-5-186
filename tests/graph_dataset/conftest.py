"""Shared small graph fixtures for converter tests."""

import gzip
import json
from pathlib import Path

import pytest

from shield_core.extraction.graph_extractor import CodeGraph, GraphEdge, GraphNode

FIXTURES = Path(__file__).parents[1] / "fixtures" / "graphs"


@pytest.fixture
def load_graph():
    def load(name):
        with gzip.open(FIXTURES / f"{name}.json.gz", "rt", encoding="utf-8") as stream:
            return CodeGraph.from_dict(json.load(stream))

    return load


@pytest.fixture
def make_graph():
    def make(nodes, edges=()):
        return CodeGraph("python", "test", "1", "test", list(nodes), list(edges))

    return make


@pytest.fixture
def tiny_graph(make_graph):
    return make_graph(
        [GraphNode(2, "CALL", "f()", "f", 2), GraphNode(1, "METHOD", "def f", "f", 1)],
        [GraphEdge(1, 2, "AST"), GraphEdge(1, 2, "CFG")],
    )
