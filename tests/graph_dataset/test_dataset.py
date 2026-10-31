"""PyG in-memory dataset loading errors are actionable."""

import pytest

pytest.importorskip("torch_geometric")

from shield_core.graph_dataset.dataset import ShieldGraphDataset


def test_missing_split_points_to_build_command(tmp_path):
    with pytest.raises(FileNotFoundError, match="build_pyg_dataset.py"):
        ShieldGraphDataset(tmp_path, "train")
