"""Access a previously built graph split through the PyG dataset interface."""

from pathlib import Path

from torch_geometric.data import InMemoryDataset

from shield_core.graph_dataset.schema import NUM_NODE_FEATURES


class ShieldGraphDataset(InMemoryDataset):
    """A read-only view of one processed split; building remains an explicit CLI action."""

    def __init__(self, root, split: str):
        self.split = split
        path = Path(root) / "processed" / f"{split}.pt"
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing {path}; run scripts/graphs/build_pyg_dataset.py first"
            )
        super().__init__(str(root))
        self.load(str(path))

    @property
    def num_node_features(self) -> int:
        return NUM_NODE_FEATURES

    @property
    def num_relations(self) -> int:
        return 6

    @classmethod
    def from_config(cls, language, config, split):
        from shield_core.paths import PYG_DATASET_DIR

        root = PYG_DATASET_DIR / "1.0" / "0.1-draft" / language / config.fingerprint()
        return cls(root, split)
