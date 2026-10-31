"""Build a versioned PyG dataset from cached CodeGraphs."""

import argparse
from pathlib import Path

from shield_core.graph_dataset.builder import build_all
from shield_core.graph_dataset.schema import ConverterConfig


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=("python", "cpp"), required=True)
    parser.add_argument("--splits", nargs="+", default=["train", "val", "test", "holdout"])
    parser.add_argument("--stub-rule", choices=("A", "B"), default="A")
    parser.add_argument("--max-nodes", default="750", help="positive integer or 'none'")
    parser.add_argument("--drop-unusable", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--out", default=None)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()
    cap = None if args.max_nodes.lower() == "none" else int(args.max_nodes)
    config = ConverterConfig(args.stub_rule, cap, drop_unusable=args.drop_unusable)
    output = build_all(args.language, config, args.splits, args.limit, args.out, args.overwrite)
    report = output / "pyg_dataset_report.md"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report.read_text(encoding="utf-8"), encoding="utf-8")
    print(output)
    print(report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
