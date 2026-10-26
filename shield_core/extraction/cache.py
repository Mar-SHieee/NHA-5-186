"""Graph cache (D5): key = sha256(code) + extractor version + schema version (+ language).

Why a cache: Joern takes seconds per file and repo scans / bulk extraction (W2-P1-02) re-see
the same code constantly. Why these key parts:
  * sha256(code)    -> same code, same graph
  * extractor ver.  -> a new Joern release may produce a different graph
  * schema version  -> we changed what a graph contains (docs/graphs/graph_schema.md)
  * language        -> same text can be parsed by different frontends
  * extension       -> .c and .cpp files are parsed by different Joern grammars
Any part changing gives a different path, so stale graphs are never served.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from shield_core.extraction.graph_extractor import (
    CodeGraph,
    GraphExtractor,
    code_sha256,
    resolve_extension,
)

DEFAULT_CACHE_DIR = Path("data/cache/graphs")  # data/ is git-ignored (plan section 4.3)

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe(part: str) -> str:
    return _UNSAFE.sub("_", part) or "_"


@dataclass(frozen=True)
class CacheKey:
    code_sha: str
    language: str
    extension: str
    extractor: str
    extractor_version: str
    schema_version: str

    @classmethod
    def for_code(
        cls, code: str, language: str, extractor: GraphExtractor, extension: str | None = None
    ) -> CacheKey:
        return cls(
            code_sha=code_sha256(code),
            language=language,
            extension=resolve_extension(language, extension),
            extractor=extractor.name,
            extractor_version=extractor.version,
            schema_version=extractor.schema_version,
        )

    def relative_path(self) -> Path:
        # Version folders first: bumping Joern or the schema starts a fresh folder, and an old
        # folder can simply be deleted. The 2-char shard keeps folders small (100k+ files).

        """
        data/cache/graphs/0.1-draft/joern-4.0.647/cpp/cpp/ab/ab12cd...json.gz
                          └schema┘  └extractor-ver┘ └lang┘└ext┘└shard┘
        :return:
        """
        return (
            Path(_safe(self.schema_version))
            / f"{_safe(self.extractor)}-{_safe(self.extractor_version)}"
            / _safe(self.language)
            / _safe(self.extension.lstrip("."))
            / self.code_sha[:2]
            / f"{self.code_sha}.json.gz"
        )


class GraphCache:
    """On-disk cache with hit/miss counters (needed by W2-P1-03)."""

    def __init__(self, root: Path | str = DEFAULT_CACHE_DIR) -> None:
        self.root = Path(root)
        self.hits = 0
        self.misses = 0

    def path_for(self, key: CacheKey) -> Path:
        return self.root / key.relative_path()

    # on cache hit:return the cached graph else retun none
    def get(self, key: CacheKey) -> CodeGraph | None:
        path = self.path_for(key)
        if not path.exists():
            return None
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return CodeGraph.from_dict(json.load(f))
        except (OSError, EOFError, ValueError, KeyError, TypeError):
            # Half-written or corrupted file (e.g. a killed overnight job): treat as a miss.
            path.unlink(missing_ok=True)
            return None

    # Write graph using the cached key
    def put(self, key: CacheKey, graph: CodeGraph) -> Path:
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file then rename: readers (other processes) never see a partial file.
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
                gz.write(json.dumps(graph.to_dict(), separators=(",", ":")).encode("utf-8"))
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return path

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def stats(self) -> dict[str, float]:
        return {"hits": self.hits, "misses": self.misses, "hit_rate": self.hit_rate}


# Decorator design pattern
class CachedGraphExtractor(GraphExtractor):
    """Wraps any GraphExtractor with a cache. Everything else just sees a GraphExtractor."""

    def __init__(self, inner: GraphExtractor, cache: GraphCache | None = None) -> None:
        self.inner = inner
        self.cache = cache or GraphCache()

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def version(self) -> str:
        return self.inner.version

    @property
    def schema_version(self) -> str:
        return self.inner.schema_version

    def extract(self, code: str, language: str, extension: str | None = None) -> CodeGraph:
        extension = resolve_extension(language, extension)
        key = CacheKey.for_code(code, language, self.inner, extension)
        graph = self.cache.get(key)
        if graph is not None:
            self.cache.hits += 1
            return graph
        self.cache.misses += 1
        graph = self.inner.extract(code, language, extension)  # failures raise and are NOT cached
        self.cache.put(key, graph)
        return graph
