"""GraphExtractor interface (D2) and the plain-Python graph it returns (W1-P1-03).

ML code (GNN dataset builder, taint features, fusion) must only import THIS module.
It never imports Joern. Joern is one implementation of GraphExtractor (joern_extractor.py);
tomorrow it could be tree-sitter-only or something else, and no ML code changes.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from shield_core.languages import registry

# Bump ONLY when the raw extractor output changes (different Joern flags, different attributes
# stored per node/edge). It is part of the cache key (D5), so a bump invalidates every cached
# graph. Changes to which node/edge types are KEPT belong to the converter version instead
# (see docs/graphs/graph_schema.md, "Versions").
GRAPH_SCHEMA_VERSION = "0.1-draft"


class ExtractionError(Exception):
    """Joern (or any extractor) failed on this input. Callers log it and skip the sample."""


# --------------------------------------------------------------------------- data


@dataclass(frozen=True)
class GraphNode:
    id: int  # Joern node id; unique inside one graph, NOT stable across runs
    type: str  # Joern label: METHOD, CALL, IDENTIFIER, ...
    code: str = ""  # source text of the node (Joern CODE); this is what CodeBERT embeds
    name: str = ""  # Joern NAME (function name, identifier name, operator name)
    line: int | None = None  # LINE_NUMBER, None for stubs


@dataclass(frozen=True)
class GraphEdge:
    src: int
    dst: int
    type: str  # Joern edge label: AST, CFG, REACHING_DEF, CALL, ARGUMENT, CDG, ...


@dataclass
class CodeGraph:
    """Raw extractor output. Filtering/feature building is the PyG converter's job (P2)."""

    language: str
    extractor: str
    extractor_version: str
    schema_version: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        # Compact lists (not one dict per node) because real graphs have thousands of nodes.
        return {
            "language": self.language,
            "extractor": self.extractor,
            "extractor_version": self.extractor_version,
            "schema_version": self.schema_version,
            "nodes": [[n.id, n.type, n.code, n.name, n.line] for n in self.nodes],
            "edges": [[e.src, e.dst, e.type] for e in self.edges],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CodeGraph:
        return cls(
            language=data["language"],
            extractor=data["extractor"],
            extractor_version=data["extractor_version"],
            schema_version=data["schema_version"],
            nodes=[GraphNode(*row) for row in data["nodes"]],
            edges=[GraphEdge(*row) for row in data["edges"]],
        )


# --------------------------------------------------------------------------- hashing


def normalize_code(code: str) -> str:
    """Make the same source hash the same on Windows and Linux (CRLF/CR -> LF)."""
    return code.replace("\r\n", "\n").replace("\r", "\n")


def code_sha256(code: str) -> str:
    return hashlib.sha256(normalize_code(code).encode("utf-8")).hexdigest()


def resolve_extension(language: str, extension: str | None = None) -> str:
    """Pick the file extension Joern will see. It changes the parse (.c = C, .cpp = C++).

    Pass the real extension when the file name is known (datasets, repo scans). With None, the
    language's first extension in shield_core/languages/<name>.yaml is used (the default for
    snippets).
    """
    spec = registry.require_enabled(language)
    if extension is None:
        return spec.extensions[0]
    ext = extension.lower()
    if not ext.startswith("."):
        ext = "." + ext
    if ext not in spec.extensions:
        raise ExtractionError(f"extension {ext!r} does not belong to language {language!r}")
    return ext


# --------------------------------------------------------------------------- interface


class GraphExtractor(ABC):
    """Turns source code into a CodeGraph. Implementations must be deterministic."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short id, e.g. 'joern'."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Pinned tool version, e.g. '4.0.647'. Part of the cache key."""

    @property
    def schema_version(self) -> str:
        return GRAPH_SCHEMA_VERSION

    @abstractmethod
    def extract(self, code: str, language: str, extension: str | None = None) -> CodeGraph:
        """Return the graph for one source string. Raise ExtractionError on failure.

        extension: real file extension if known (see resolve_extension), else None.
        """
