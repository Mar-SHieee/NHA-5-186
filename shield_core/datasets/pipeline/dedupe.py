"""SHIELD parquet deduplication.

Run from the repository root:  python -m shield_core.datasets.pipeline.dedupe

Reads every unified-schema parquet in data/interim, writes <dataset>_deduped.parquet for each
and docs/datasets/audits/dedupe_report.md. Inputs are never modified.

Rows are the same code when they share a token-based key (Python keeps NEWLINE/INDENT/DEDENT).
Two extra links catch copies the strict key misses:
  * layout-insensitive Python keys, for sources without line breaks (Zenodo);
  * the same text recorded under different languages (loader mislabel).
Labels, CWEs and CVEs are resolved per cluster; 0/1 conflicts are dropped from every dataset.
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

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from shield_core.datasets import schema
from shield_core.languages import registry
from shield_core.languages.registry import LanguageSpec
from shield_core.paths import DOCS_AUDITS_DIR, REPO_ROOT

PROJECT_ROOT = REPO_ROOT
PRIORITY_ORDER = (
    "megavul",
    "bigvul",
    "cvefixes_cpp",
    "cvefixes_python",
    "zenodo_python",
)
EXCLUDED_NAME_PARTS = ("sample", "deduped")
METADATA_COLUMNS = ("project", "commit", "fixed_code", "date", "cve")
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
_WHITESPACE = re.compile(r"\s+")
_TEMP_COLUMNS = ["_layout_key", "_squash_key", "_flat", "_xkey"]


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


class PythonLayoutlessNormalizer:
    """Python tokens without comments and without any line/indent structure.

    Returns "" when the code cannot be tokenized (no layout-insensitive key is then made).
    """

    _SKIP = frozenset(
        {
            tokenize.COMMENT,
            tokenize.NL,
            tokenize.NEWLINE,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.ENCODING,
            tokenize.ENDMARKER,
        }
    )

    def normalize(self, code: str) -> str:
        try:
            parts = []
            for token in tokenize.generate_tokens(io.StringIO(code).readline):
                if token.type in self._SKIP:
                    continue
                if token.type == tokenize.ERRORTOKEN and token.string.strip():
                    return ""
                parts.append([tokenize.tok_name[token.type], token.string])
            return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
        except (tokenize.TokenError, IndentationError, SyntaxError, UnicodeError):
            return ""


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
    conflict_cross_dataset: int = 0
    merged_cwe_groups: int = 0
    merged_cve_groups: int = 0
    layout_merges: int = 0
    layout_rows_linked: int = 0
    cross_language_merges: int = 0
    cross_language_rows_linked: int = 0


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


def _present(value: object) -> bool:
    """True when a metadata cell carries information (empty list / blank string = missing)."""
    if value is None or value is pd.NA:
        return False
    if isinstance(value, (list, tuple, set, np.ndarray)):
        return len(value) > 0
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, float):
        return not np.isnan(value)
    return True


class DedupeEngine:
    def __init__(
        self,
        normalizers: dict[str, Normalizer],
        fallback: Normalizer,
        hasher: Hasher,
        metadata_columns: tuple[str, ...],
        languages: frozenset[str] | None = None,
        layoutless: dict[str, Normalizer] | None = None,
    ):
        self._normalizers = normalizers
        self._fallback = fallback
        self._hasher = hasher
        self._metadata_columns = metadata_columns
        self._languages = languages
        self._layoutless = layoutless or {}

    def _with_hash(self, name: str, df: pd.DataFrame) -> pd.DataFrame:
        missing = set(REQUIRED_COLUMNS) - set(df.columns)
        if missing:
            raise ValueError(f"{name}: missing unified schema columns: {sorted(missing)}")
        df = df.copy()
        strict, layout_keys, squash_keys, flat, xkeys = [], [], [], [], []
        for code, language in zip(df["code"], df["language"], strict=True):
            if not isinstance(code, str) or not code.strip():
                strict.append("")
                layout_keys.append("")
                squash_keys.append("")
                flat.append(False)
                xkeys.append("")
                continue
            lang = str(language)
            normalized = self._normalizers.get(lang, self._fallback).normalize(code)
            xkeys.append(self._hasher.hash("xlang\0" + _WHITESPACE.sub("", code)))
            strict.append(self._hasher.hash(lang + "\0" + normalized) if normalized else "")

            layoutless = self._layoutless.get(lang)
            if layoutless is None:
                layout_keys.append("")
                squash_keys.append("")
                flat.append(False)
                continue
            text = layoutless.normalize(code)
            layout_keys.append(self._hasher.hash("layout\0" + lang + "\0" + text) if text else "")
            squash_keys.append(
                self._hasher.hash("squash\0" + lang + "\0" + _WHITESPACE.sub("", code))
            )
            flat.append("\n" not in code.replace("\r\n", "\n").strip())
        df["code_hash"] = strict
        df["_layout_key"] = layout_keys
        df["_squash_key"] = squash_keys
        df["_flat"] = flat
        df["_xkey"] = xkeys
        return df

    def _filter_language(self, name: str, df: pd.DataFrame, report: DedupeReport) -> pd.DataFrame:
        if self._languages is None:
            return df
        mask = df["language"].isin(self._languages)
        report.stats[name].filtered = int((~mask).sum())
        dropped = df.loc[~mask, "language"].fillna("<NA>").value_counts()
        report.stats[name].filtered_languages = {str(k): int(v) for k, v in dropped.items()}
        return df.loc[mask].copy()

    def _link_cross_language(self, frames: dict[str, pd.DataFrame], report: DedupeReport) -> None:
        """Link identical text recorded under different languages (one strict hash per language)."""
        groups: dict[str, dict[str, set[str]]] = {}
        for df in frames.values():
            if df.empty:
                continue
            for xkey, strict, lang in zip(
                df["_xkey"], df["code_hash"], df["language"].astype(str), strict=True
            ):
                if xkey:
                    groups.setdefault(xkey, {}).setdefault(lang, set()).add(strict)
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        for by_lang in groups.values():
            if len(by_lang) < 2 or any(len(v) != 1 for v in by_lang.values()):
                continue
            hashes = sorted(next(iter(v)) for v in by_lang.values())
            for other in hashes[1:]:
                ra, rb = find(hashes[0]), find(other)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
                    report.cross_language_merges += 1
        if not parent:
            return
        for name, df in frames.items():
            if df.empty:
                continue
            linked = df["code_hash"].map(find)
            report.cross_language_rows_linked += int((linked != df["code_hash"]).sum())
            frames[name] = df.assign(code_hash=linked)

    def _link_layout_variants(self, frames: dict[str, pd.DataFrame], report: DedupeReport) -> None:
        """Link flattened rows to their single laid-out copy."""
        flat_keys: dict[str, set[str]] = {}
        laid_out_keys: dict[str, set[str]] = {}
        for df in frames.values():
            if df.empty:
                continue
            for strict, layout, squash, is_flat in zip(
                df["code_hash"],
                df["_layout_key"],
                df["_squash_key"],
                df["_flat"],
                strict=True,
            ):
                for key in (layout, squash):
                    if key:
                        target = flat_keys if is_flat else laid_out_keys
                        target.setdefault(key, set()).add(strict)

        parent: dict[str, str] = {}

        def find(x: str) -> str:
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                low, high = sorted((ra, rb))
                parent[high] = low
                report.layout_merges += 1

        for key, flat_members in flat_keys.items():
            members = sorted(flat_members)
            for other in members[1:]:
                union(members[0], other)
            laid_out = laid_out_keys.get(key, set())
            if len(laid_out) == 1:
                union(members[0], next(iter(laid_out)))

        for name, df in frames.items():
            if not df.empty and parent:
                linked = df["code_hash"].map(find)
                report.layout_rows_linked += int((linked != df["code_hash"]).sum())
                df = df.assign(code_hash=linked)
            frames[name] = df.drop(columns=_TEMP_COLUMNS)

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

        self._link_cross_language(frames, report)
        self._link_layout_variants(frames, report)

        label_sets: dict[str, set[int]] = {}
        key_datasets: dict[str, set[str]] = {}
        for name, df in frames.items():
            if df.empty:
                continue
            for key, labels in df.groupby("code_hash", sort=False)["label"]:
                label_sets.setdefault(key, set()).update(int(x) for x in labels.dropna().unique())
                key_datasets.setdefault(key, set()).add(name)
        conflicting = {key for key, labels in label_sets.items() if len(labels) > 1}
        report.conflict_groups = len(conflicting)
        report.conflict_cross_dataset = sum(len(key_datasets[k]) > 1 for k in conflicting)
        for name, df in frames.items():
            conflict = df["code_hash"].isin(conflicting)
            report.stats[name].conflicts = int(conflict.sum())
            frames[name] = df.loc[~conflict].copy()

        all_cwes: dict[str, set[str]] = {}
        all_cves: dict[str, set[str]] = {}
        for df in frames.values():
            for key, cwe in zip(df["code_hash"], df["cwe"], strict=True):
                all_cwes.setdefault(key, set()).update(_cwes(cwe))
            if "cve" in df.columns:
                for key, cve in zip(df["code_hash"], df["cve"], strict=True):
                    all_cves.setdefault(key, set()).update(schema.normalize_cve(cve))
        report.merged_cwe_groups = sum(len(labels) > 1 for labels in all_cwes.values())
        report.merged_cve_groups = sum(len(ids) > 1 for ids in all_cves.values())

        for name, df in frames.items():
            if df.empty:
                continue
            columns = [c for c in self._metadata_columns if c in df.columns]
            if columns:
                filled = sum(df[c].map(_present).astype(int) for c in columns)
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
                unique["cwe"] = pd.Series(
                    [sorted(all_cwes[key]) for key in unique["code_hash"]],
                    index=unique.index,
                    dtype="object",
                )
                if "cve" in unique.columns:
                    unique["cve"] = pd.Series(
                        [
                            schema.normalize_cve(sorted(all_cves[key]))
                            for key in unique["code_hash"]
                        ],
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
        allowed = set(self._priority)
        names = [p.stem for p in self._directory.glob("*.parquet") if p.stem.lower() in allowed]
        if not names:
            raise FileNotFoundError(
                f"No supported dataset parquet files found in {self._directory}"
            )
        return sorted(names, key=self._rank)

    def load(self) -> dict[str, pd.DataFrame]:
        result = {}
        for name in self._discover():
            path = self._directory / f"{name}.parquet"
            columns = pq.read_schema(path).names
            if columns != schema.COLUMNS:
                raise ValueError(
                    f"{name}: expected schema {schema.SCHEMA_VERSION} columns "
                    f"{schema.COLUMNS}, got {columns}"
                )
            result[name] = schema.from_parquet(path)
        return result

    def save(self, name: str, df: pd.DataFrame) -> None:
        path = self._directory / f"{name}_deduped.parquet"
        df = df.reset_index(drop=True)[schema.COLUMNS]
        issues = schema.validate(df)
        if issues:
            raise ValueError(f"{name} deduped validation failed: {issues}")
        schema.to_parquet(df, path)  # stable Arrow schema, also for empty / all-empty-list data


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
                f"Conflicting code-hash groups (0 vs 1): {report.conflict_groups:,} "
                f"(across datasets: {report.conflict_cross_dataset:,}, "
                f"inside one dataset: {report.conflict_groups - report.conflict_cross_dataset:,})",
                f"Code-hash groups with multiple CWE labels: {report.merged_cwe_groups:,}",
                f"Code-hash groups with multiple CVE ids: {report.merged_cve_groups:,}",
                "",
                "Layout-insensitive Python matching (sources without line breaks, e.g. Zenodo): "
                f"{report.layout_merges:,} key merges, "
                f"{report.layout_rows_linked:,} rows linked to another copy.",
                "",
                "Same code recorded under different languages (loader mislabel): "
                f"{report.cross_language_merges:,} key merges, "
                f"{report.cross_language_rows_linked:,} rows linked to another copy.",
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
                    "- Same-code CWE and CVE labels are unioned into the retained "
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
                    "- Python code without line breaks is matched to its laid-out copy by "
                    "layout-insensitive keys; two laid-out versions are never merged this way."
                ),
                (
                    "- No CVE/commit/project grouping or semantic clone "
                    "detection is performed; use group-aware splitting later."
                ),
                "- All original input parquet files remain unchanged.",
                "- project/commit/date metadata come from the selected representative row;",
                "  deduplication does not preserve every provenance relation.",
                (
                    "- Keep the *_commit_cve_mapping.parquet files "
                    "(CVEfixes, Big-Vul, MegaVul, Zenodo) separately for splitting."
                ),
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


def build_layoutless_normalizers(specs: list[LanguageSpec]) -> dict[str, Normalizer]:
    """Layout-insensitive keys only make sense for indentation-sensitive languages (Python)."""
    layoutless = PythonLayoutlessNormalizer()
    return {spec.name: layoutless for spec in specs if ".py" in spec.extensions}


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
            layoutless=build_layoutless_normalizers(registry.all_languages()),
        ),
        report_writer=MarkdownReportWriter(DOCS_AUDITS_DIR / "dedupe_report.md"),
    )


if __name__ == "__main__":
    build_default_runner().run()
