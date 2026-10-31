"""Convert cached CodeGraphs into versioned PyG datasets.

Imports stay lazy so schema and filtering remain usable without the optional PyG dependency.
"""

from shield_core.graph_dataset.schema import CONVERTER_VERSION, ConverterConfig

__all__ = ["CONVERTER_VERSION", "ConverterConfig"]
