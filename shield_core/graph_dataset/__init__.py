"""Convert cached CodeGraphs into versioned PyG datasets.

Imports stay lazy so schema and filtering remain usable without the optional PyG dependency.
"""

from shield_core.graph_dataset.schema import CONVERTER_VERSION, ConverterConfig

__all__ = [
    "CONVERTER_VERSION",
    "ConverterConfig",
    "filter_graph",
    "to_data",
    "build_all",
    "ShieldGraphDataset",
]


def __getattr__(name: str):
    """Load optional tensor modules only when a caller asks for them."""
    if name == "filter_graph":
        from shield_core.graph_dataset.filtering import filter_graph

        return filter_graph
    if name == "to_data":
        from shield_core.graph_dataset.to_pyg import to_data

        return to_data
    if name == "build_all":
        from shield_core.graph_dataset.builder import build_all

        return build_all
    if name == "ShieldGraphDataset":
        from shield_core.graph_dataset.dataset import ShieldGraphDataset

        return ShieldGraphDataset
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
