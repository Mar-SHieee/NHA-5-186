"""Freeze a Joern GraphML export as a compact deterministic CodeGraph fixture."""

import argparse
import gzip
import json
from pathlib import Path

from shield_core.extraction.graph_extractor import GRAPH_SCHEMA_VERSION, CodeGraph
from shield_core.extraction.joern_extractor import DEFAULT_JOERN_VERSION, parse_graphml


def export(source: Path, language: str, name: str, output_dir: Path) -> Path:
    nodes, edges = parse_graphml(source)
    graph = CodeGraph(language, "joern", DEFAULT_JOERN_VERSION, GRAPH_SCHEMA_VERSION, nodes, edges)
    output = output_dir / f"{name}.json.gz"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as stream:
        stream.write(json.dumps(graph.to_dict(), separators=(",", ":")).encode("utf-8"))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graphml", type=Path)
    parser.add_argument("--language", choices=("python", "cpp"), required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("tests/fixtures/graphs"))
    args = parser.parse_args()
    print(export(args.graphml, args.language, args.name, args.output_dir))


if __name__ == "__main__":
    main()
