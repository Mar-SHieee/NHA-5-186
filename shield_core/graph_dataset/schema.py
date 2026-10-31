"""Stable feature and edge identifiers for processed graph datasets."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

NODE_TYPES = (
    "METHOD",
    "METHOD_PARAMETER_IN",
    "METHOD_RETURN",
    "BLOCK",
    "CALL",
    "IDENTIFIER",
    "LITERAL",
    "LOCAL",
    "FIELD_IDENTIFIER",
    "RETURN",
    "METHOD_REF",
    "CONTROL_STRUCTURE",
)
EDGE_TYPES = {"AST": 0, "CFG": 1, "REACHING_DEF": 2, "CALL": 3, "ARGUMENT": 4, "CDG": 5}
NUM_FLAGS = 3
NUM_NODE_FEATURES = len(NODE_TYPES) + NUM_FLAGS
CONVERTER_VERSION = "1.0"
WRAPPER_METHODS = frozenset({"<module>", "<global>"})


@dataclass(frozen=True)
class ConverterConfig:
    """Options that affect graph selection and therefore processed dataset identity."""

    stub_rule: str = "A"
    max_nodes: int | None = 750
    edge_types: tuple[str, ...] = tuple(EDGE_TYPES)
    drop_unusable: bool = False

    def __post_init__(self) -> None:
        if self.stub_rule not in {"A", "B"}:
            raise ValueError("stub_rule must be 'A' or 'B'")
        if self.max_nodes is not None and self.max_nodes < 1:
            raise ValueError("max_nodes must be None or >= 1")
        if (
            len(set(self.edge_types)) != len(self.edge_types)
            or not set(self.edge_types) <= EDGE_TYPES.keys()
        ):
            raise ValueError("edge_types must contain unique known edge names")

    def to_dict(self) -> dict:
        return asdict(self)

    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()[:10]


def text_hash64(text: str) -> int:
    """Hash node text into PyTorch's signed int64 range for joining embedding caches."""
    value = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)
    return value - 2**64 if value >= 2**63 else value
