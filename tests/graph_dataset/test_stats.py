"""Statistics and cap-selection summaries."""

from shield_core.graph_dataset.stats import cap_table, size_summary


def test_summary_and_label_cap_gap():
    rows = [
        {"status": "ok", "n_nodes": 10, "n_edges": 5, "label": 0},
        {"status": "over_node_cap", "n_nodes": 20, "n_edges": 8, "label": 1},
    ]
    assert size_summary(rows)["n_nodes"]["max"] == 10
    caps = cap_table(rows, [10])[0]
    assert caps["label_0"] == 1.0
    assert caps["label_1"] == 0.0
    assert caps["label_gap_pp"] == 100.0
