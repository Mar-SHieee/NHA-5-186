"""SHIELD language-aware, provenance-conscious parquet deduplication.

Run from repository root:
    python -m shield_core.datasets.dedupe

Reads every non-sample, non-deduped parquet in data/interim, writes a
<dataset>_deduped.parquet for EACH input (including empty results), and
writes docs/dedupe_report.md. Input parquet files are never modified.
"""

from __future__ import annotations

import hashlib
import io
import itertools
import json
import re
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import pandas as pd

from languages import registry
from languages.registry import LanguageSpec

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRIORITY_ORDER = ("megavul", "bigvul")
EXCLUDED_NAME_PARTS = ("sample", "deduped")
METADATA_COLUMNS = ("project", "commit", "fixed_code")
REQUIRED_COLUMNS = ("code", "language", "label", "cwe")
REPORT_HEADERS = (
    "dataset",
    "original",
    "language-filtered",
    "empty",
    "label conflicts",
    "internal dups",
    "cross dups",
    "final",
)


class Normalizer(Protocol):
    def normalize(self, code: str) -> str: ...


class Hasher(Protocol):
    def hash(self, text: str) -> str: ...


class DatasetRepository(Protocol):
    def load(self) -> dict[str, pd.DataFrame]: ...
    def save(self, name: str, df: pd.DataFrame) -> None: ...


class ReportWriter(Protocol):
    def write(self, report: "DedupeReport") -> None: ...


class PythonTokenNormalizer:
    """Ignore comments/formatting, retain string contents and indentation.

    tokenize may fail on partial code fragments. Fall back to exact source
    (except line-ending normalization), rather than risk false equivalence.
    """

    def normalize(self, code: str) -> str:
        try:
            tokens = tokenize.generate_tokens(io.StringIO(code).readline)
            parts = []
            for token in tokens:
                if token.type in (
                    tokenize.COMMENT,
                    tokenize.NL,
                    tokenize.ENCODING,
                    tokenize.ENDMARKER,
                ):
                    continue
                if token.type == tokenize.ERRORTOKEN and token.string.strip():
                    return code.replace("\r\n", "\n")
                if token.type in (tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE):
                    parts.append([tokenize.tok_name[token.type], ""])
                else:
                    parts.append([tokenize.tok_name[token.type], token.string])
            return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
        except (tokenize.TokenError, IndentationError, SyntaxError, UnicodeError):
            return code.replace("\r\n", "\n")


# Token-aware C-family normalizer: comments are discarded; quoted strings and
# character literals remain intact; tokens are separated in the hash encoding.
_C_LEX = re.compile(
    r"(?P<comment>//[^\n]*|/\*[\s\S]*?\*/)|"
    r'(?P<string>(?:u8|u|U|L)?"(?:\\[\s\S]|[^"\\])*"|(?:u8|u|U|L)?\'(?:\\[\s\S]|[^\'\\])*\')|'
    r"(?P<identifier>[A-Za-z_$][A-Za-z0-9_$]*)|"
    r"(?P<number>(?:\d+(?:\.\d+)?|\.\d+)(?:[eEpP][+-]?\d+)?[A-Za-z0-9_]*)|"
    r"(?P<punct>[^\s])",
    re.MULTILINE,
)


class CStyleTokenNormalizer:
    def normalize(self, code: str) -> str:
        tokens = []
        for match in _C_LEX.finditer(code):
            if match.lastgroup != "comment":
                tokens.append(match.group())
        return json.dumps(tokens, ensure_ascii=False, separators=(",", ":"))


class ConservativeNormalizer:
    def normalize(self, code: str) -> str:
        return code.replace("\r\n", "\n")


class Sha256Hasher:
    def hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class DatasetStats:
    original: int = 0
    empty: int = 0
    conflicts: int = 0
    internal: int = 0
    cross: int = 0
    final: int = 0
    filtered: int = 0
    filtered_languages: dict[str, int] = field(default_factory=dict)


@dataclass
class DedupeReport:
    stats: dict[str, DatasetStats] = field(default_factory=dict)
    overlaps: dict[tuple[str, str], int] = field(default_factory=dict)
    conflict_groups: int = 0
    merged_cwe_groups: int = 0


def _cwes(value: object) -> list[str]:
    """Accept ndarray/list/tuple/string/NA; preserve CWE identifiers only."""
    if value is None or value is pd.NA:
        return []
    if isinstance(value, str):
        if not value.strip():
            return []
        if value.lstrip().startswith("["):
            try:
                decoded = json.loads(value)
                if isinstance(decoded, list):
                    return sorted({str(x).strip() for x in decoded if str(x).strip()})
            except ValueError:
                pass
        return [value.strip()]
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (list, tuple, set)):
        return sorted({str(x).strip() for x in value if x is not None and str(x).strip()})
    try:
        if pd.isna(value):
            return []
    except (TypeError, ValueError):
        pass
    return [str(value)]


class DedupeEngine:
    def __init__(
        self,
        normalizers: dict[str, Normalizer],
        fallback: Normalizer,
        hasher: Hasher,
        metadata_columns: tuple[str, ...],
        languages: frozenset[str] | None = None,
    ):
        self._normalizers = normalizers
        self._fallback = fallback
        self._hasher = hasher
        self._metadata_columns = metadata_columns
        self._languages = languages

    def _with_hash(self, name: str, df: pd.DataFrame) -> pd.DataFrame:
        missing = set(REQUIRED_COLUMNS) - set(df.columns)
        if missing:
            raise ValueError(f"{name}: missing unified schema columns: {sorted(missing)}")
        df = df.copy()
        keys = []
        for code, language in zip(df["code"], df["language"], strict=True):
            if not isinstance(code, str) or not code.strip():
                keys.append("")
                continue
            lang = str(language)
            normalized = self._normalizers.get(lang, self._fallback).normalize(code)
            # Include language in key so Python/C++ cannot collide.
            keys.append(self._hasher.hash(lang + "\0" + normalized) if normalized else "")
        df["code_hash"] = keys
        return df

    def _filter_language(self, name: str, df: pd.DataFrame, report: DedupeReport) -> pd.DataFrame:
        if self._languages is None:
            return df
        mask = df["language"].isin(self._languages)
        report.stats[name].filtered = int((~mask).sum())
        dropped = df.loc[~mask, "language"].fillna("<NA>").value_counts()
        report.stats[name].filtered_languages = {str(k): int(v) for k, v in dropped.items()}
        # Empty output is legitimate when a dataset contains only disabled languages.
        return df.loc[mask].copy()

    def run(
        self, datasets: dict[str, pd.DataFrame]
    ) -> tuple[dict[str, pd.DataFrame], DedupeReport]:
        report = DedupeReport(
            stats={n: DatasetStats(original=len(df)) for n, df in datasets.items()}
        )
        frames = {}
        for name, source in datasets.items():
            selected = self._filter_language(name, source, report)
            df = self._with_hash(name, selected)
            empty = df["code_hash"].eq("")
            report.stats[name].empty = int(empty.sum())
            frames[name] = df.loc[~empty].copy()

        # Detect binary-label conflicts across ALL input datasets, not just within each.
        label_sets: dict[str, set[int]] = {}
        for df in frames.values():
            if df.empty:
                continue
            for key, labels in df.groupby("code_hash", sort=False)["label"]:
                label_sets.setdefault(key, set()).update(int(x) for x in labels.dropna().unique())
        conflicting = {key for key, labels in label_sets.items() if len(labels) > 1}
        report.conflict_groups = len(conflicting)
        for name, df in frames.items():
            conflict = df["code_hash"].isin(conflicting)
            report.stats[name].conflicts = int(conflict.sum())
            frames[name] = df.loc[~conflict].copy()

        # CWE labels are accumulated across duplicates before any row is dropped.
        # Preserve original eight-column schema: CWE stays list-like.
        all_cwes: dict[str, set[str]] = {}
        for df in frames.values():
            for key, value in zip(df["code_hash"], df["cwe"], strict=True):
                all_cwes.setdefault(key, set()).update(_cwes(value))
        report.merged_cwe_groups = sum(len(labels) > 1 for labels in all_cwes.values())

        for name, df in frames.items():
            if df.empty:
                continue
            columns = [c for c in self._metadata_columns if c in df.columns]
            if columns:
                filled = df[columns].notna().sum(axis=1)
                df = df.assign(_filled=filled).sort_values(
                    "_filled", ascending=False, kind="stable"
                )
            before = len(df)
            df = df.drop_duplicates(subset="code_hash", keep="first")
            report.stats[name].internal = before - len(df)
            if "_filled" in df:
                df = df.drop(columns="_filled")
            frames[name] = df.sort_index()

        hashes = {name: set(df["code_hash"]) for name, df in frames.items()}
        report.overlaps = {
            (a, b): len(hashes[a] & hashes[b]) for a, b in itertools.combinations(frames, 2)
        }
        seen: set[str] = set()
        output: dict[str, pd.DataFrame] = {}
        for name, df in frames.items():
            duplicate = df["code_hash"].isin(seen)
            report.stats[name].cross = int(duplicate.sum())
            unique = df.loc[~duplicate].copy()
            seen.update(unique["code_hash"])
            if len(unique):
                # Assign object arrays explicitly, compatible with Parquet and schema.conform.
                unique["cwe"] = pd.Series(
                    [sorted(all_cwes[key]) for key in unique["code_hash"]],
                    index=unique.index,
                    dtype="object",
                )
            report.stats[name].final = len(unique)
            output[name] = unique.drop(columns="code_hash").reset_index(drop=True)
        return output, report


class ParquetRepository:
    def __init__(
        self, directory: Path, priority: tuple[str, ...], excluded_name_parts: tuple[str, ...]
    ):
        self._directory = directory
        self._priority = priority
        self._excluded = excluded_name_parts

    def _rank(self, name: str) -> tuple[int, str]:
        return (self._priority.index(name) if name in self._priority else len(self._priority), name)

    def _discover(self) -> list[str]:
        names = [
            p.stem
            for p in self._directory.glob("*.parquet")
            if not any(part in p.stem.lower() for part in self._excluded)
        ]
        if not names:
            raise FileNotFoundError(f"No source parquet datasets found in {self._directory}")
        return sorted(names, key=self._rank)

    def load(self) -> dict[str, pd.DataFrame]:
        return {
            name: pd.read_parquet(self._directory / f"{name}.parquet") for name in self._discover()
        }

    def save(self, name: str, df: pd.DataFrame) -> None:
        path = self._directory / f"{name}_deduped.parquet"
        df.reset_index(drop=True).to_parquet(path, compression="zstd", index=False)


class MarkdownReportWriter:
    def __init__(self, path: Path):
        self._path = path

    def write(self, report: DedupeReport) -> None:
        lines = [
            "# Dedupe report",
            "",
            "| " + " | ".join(REPORT_HEADERS) + " |",
            "| " + " | ".join("---" for _ in REPORT_HEADERS) + " |",
        ]
        for name, s in report.stats.items():
            lines.append(
                f"| {name} | {s.original:,} | {s.filtered:,} | {s.empty:,} | "
                f"{s.conflicts:,} | {s.internal:,} | {s.cross:,} | {s.final:,} |"
            )
        lines.extend(
            [
                "",
                f"Conflicting code-hash groups (0 vs 1): {report.conflict_groups:,}",
                f"Code-hash groups with multiple CWE labels: {report.merged_cwe_groups:,}",
                "",
                "## Languages excluded by registry",
                "",
            ]
        )
        for name, s in report.stats.items():
            if s.filtered_languages:
                lines.append(f"- {name}: {s.filtered_languages}")
        lines.extend(
            [
                "",
                "## Pairwise overlaps after internal dedupe, before cross-dataset dedupe",
                "",
                "| dataset A | dataset B | shared hashes |",
                "| --- | --- | --- |",
            ]
        )
        for (a, b), count in report.overlaps.items():
            lines.append(f"| {a} | {b} | {count:,} |")
        lines.extend(
            [
                "",
                "## Policy",
                "",
                "- Language names and enabled status come from the language registry YAML files.",
                (
                    "- One retained row per normalized code hash "
                    "across datasets; source priority determines owner."
                ),
                (
                    "- Same-code CWE labels are unioned into the retained "
                    "row (multi-label); provenance of other rows is not retained."
                ),
                (
                    "- Conflicting binary labels (0/1) for the "
                    "same hash are excluded from every dataset."
                ),
                (
                    "- Normalization is token-based for Python and "
                    "C-family languages, conservative for unknown languages."
                ),
                (
                    "- No CVE/commit/project grouping or semantic clone "
                    "detection is performed; use group-aware splitting later."
                ),
                "- All original input parquet files remain unchanged.",
            ]
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class DedupeRunner:
    def __init__(
        self, repository: DatasetRepository, engine: DedupeEngine, report_writer: ReportWriter
    ):
        self._repository = repository
        self._engine = engine
        self._report_writer = report_writer

    def run(self) -> DedupeReport:
        datasets = self._repository.load()
        deduped, report = self._engine.run(datasets)
        for name, df in deduped.items():
            self._repository.save(name, df)
        self._report_writer.write(report)
        return report


def build_normalizers(specs: list[LanguageSpec]) -> dict[str, Normalizer]:
    python = PythonTokenNormalizer()
    c_family = CStyleTokenNormalizer()
    by_extension: dict[str, Normalizer] = {
        ".py": python,
        ".c": c_family,
        ".h": c_family,
        ".cc": c_family,
        ".cpp": c_family,
        ".cxx": c_family,
        ".hpp": c_family,
        ".java": c_family,
    }
    normalizers = {}
    for spec in specs:
        normalizer = next(
            (by_extension[ext] for ext in spec.extensions if ext in by_extension), None
        )
        if normalizer is not None:
            normalizers[spec.name] = normalizer
    return normalizers


def build_default_runner(languages: frozenset[str] | None = None) -> DedupeRunner:
    selected = languages if languages is not None else frozenset(registry.enabled_languages())
    return DedupeRunner(
        repository=ParquetRepository(
            PROJECT_ROOT / "data" / "interim", PRIORITY_ORDER, EXCLUDED_NAME_PARTS
        ),
        engine=DedupeEngine(
            normalizers=build_normalizers(registry.all_languages()),
            fallback=ConservativeNormalizer(),
            hasher=Sha256Hasher(),
            metadata_columns=METADATA_COLUMNS,
            languages=selected,
        ),
        report_writer=MarkdownReportWriter(PROJECT_ROOT / "docs" / "dedupe_report.md"),
    )


if __name__ == "__main__":
    build_default_runner().run()
