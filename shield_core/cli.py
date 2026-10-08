import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from languages import registry
from shield_core.interface import predict


def fail(message: str):
    print(f"err: {message}", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shield", description="SHIELD vulnerability scanner")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="scan one source file")
    scan.add_argument("path", help="file to scan")
    scan.add_argument("--language", help="override language detection")
    return parser


def cmd_scan(path_arg: str, language_arg: str | None):
    path = Path(path_arg)
    if path.is_dir():
        return fail("pass a single file")
    if not path.is_file():
        return fail(f"file not found: {path}")

    enabled = ", ".join(registry.enabled_languages())

    if language_arg:
        try:
            spec = registry.require_enabled(language_arg)
        except registry.RegistryError as e:
            return fail(str(e))

    else:
        spec = registry.language_for_path(path_arg)
        if spec is None:
            return fail(f"unsupported file type / Enabled languages: {enabled}")
        if not spec.enabled:
            return fail(f"unsupported language: {spec.name} / Enabled languages: {enabled}")

    code = path.read_text(encoding="utf-8", errors="replace")
    result = predict(code, spec.name)
    print(json.dumps(asdict(result), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "scan":
        return cmd_scan(args.path, args.language)
    return fail(f"unknown command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
