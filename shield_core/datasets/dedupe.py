import hashlib
import io
import itertools
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

_C_TOKEN = re.compile(
    r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|//[^\n]*|/\*.*?\*/',
    re.DOTALL,
)
_WHITESPACE = re.compile(r"\s+")


class CommentRemover(Protocol):
    def remove(self, code: str) -> str: ...


class Normalizer(Protocol):
    def normalize(self, code: str) -> str: ...


class Hasher(Protocol):
    def hash(self, text: str) -> str: ...


class DatasetRepository(Protocol):
    def load(self) -> dict[str, pd.DataFrame]: ...

    def save(self, name: str, df: pd.DataFrame) -> None: ...


class ReportWriter(Protocol):
    def write(self, report: "DedupeReport") -> None: ...


class CStyleCommentRemover:
    def remove(self, code: str) -> str:
        return _C_TOKEN.sub(lambda m: m.group(0) if m.group(0)[0] in "\"'" else " ", code)


class PythonCommentRemover:
    def remove(self, code: str) -> str:
        try:
            tokens = tokenize.generate_tokens(io.StringIO(code).readline)
            return " ".join(t.string for t in tokens if t.type != tokenize.COMMENT)
        except (tokenize.TokenError, IndentationError, SyntaxError):
            return code


class NoCommentRemover:
    def remove(self, code: str) -> str:
        return code


class StrippingNormalizer:
    def __init__(self, comment_remover: CommentRemover):
        self._comment_remover = comment_remover

    def normalize(self, code: str) -> str:
        return _WHITESPACE.sub("", self._comment_remover.remove(code))


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

    def run(
        self, datasets: dict[str, pd.DataFrame]
    ) -> tuple[dict[str, pd.DataFrame], DedupeReport]:
        report = DedupeReport(
            stats={n: DatasetStats(original=len(df)) for n, df in datasets.items()}
        )
        selected = {n: self._filter_language(n, df, report) for n, df in datasets.items()}
        frames = self._drop_empty({n: self._with_hash(df) for n, df in selected.items()}, report)
        frames = self._drop_conflicts(frames, report)
        frames = self._drop_internal(frames, report)
        report.overlaps = self._measure_overlaps(frames)
        frames = self._drop_cross(frames, report)

        result = {}
        for name, df in frames.items():
            report.stats[name].final = len(df)
            result[name] = df.drop(columns="code_hash").reset_index(drop=True)
        return result, report

    def _filter_language(self, name: str, df: pd.DataFrame, report: DedupeReport) -> pd.DataFrame:
        if self._languages is None:
            return df
        mask = df["language"].isin(self._languages)
        if len(df) and not mask.any():
            found = sorted(df["language"].dropna().unique())
            raise ValueError(
                f"{name}: no rows left after language filter {sorted(self._languages)}; "
                f"language values found: {found}"
            )
        report.stats[name].filtered = int((~mask).sum())
        dropped = df.loc[~mask, "language"].fillna("<NA>").value_counts()
        report.stats[name].filtered_languages = {str(k): int(v) for k, v in dropped.items()}
        return df[mask]

    def _normalizer_for(self, language: str) -> Normalizer:
        return self._normalizers.get(language, self._fallback)

    def _hash_row(self, code: object, language: str) -> str:
        if not isinstance(code, str):
            return ""
        normalized = self._normalizer_for(language).normalize(code)
        return self._hasher.hash(normalized) if normalized else ""

    def _with_hash(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["code_hash"] = [
            self._hash_row(code, language)
            for code, language in zip(df["code"], df["language"], strict=True)
        ]
        return df

    @staticmethod
    def _drop_empty(
        frames: dict[str, pd.DataFrame], report: DedupeReport
    ) -> dict[str, pd.DataFrame]:
        kept = {}
        for name, df in frames.items():
            mask = df["code_hash"] != ""
            report.stats[name].empty = int((~mask).sum())
            kept[name] = df[mask]
        return kept

    @staticmethod
    def _drop_conflicts(
        frames: dict[str, pd.DataFrame], report: DedupeReport
    ) -> dict[str, pd.DataFrame]:
        combined = pd.concat(
            [df[["code_hash", "label"]] for df in frames.values()], ignore_index=True
        )
        label_counts = combined.groupby("code_hash")["label"].nunique()
        conflicting = set(label_counts[label_counts > 1].index)
        report.conflict_groups = len(conflicting)

        kept = {}
        for name, df in frames.items():
            mask = ~df["code_hash"].isin(conflicting)
            report.stats[name].conflicts = int((~mask).sum())
            kept[name] = df[mask]
        return kept

    def _drop_internal(
        self, frames: dict[str, pd.DataFrame], report: DedupeReport
    ) -> dict[str, pd.DataFrame]:
        kept = {}
        for name, df in frames.items():
            unique = self._keep_most_complete(df)
            report.stats[name].internal = len(df) - len(unique)
            kept[name] = unique
        return kept

    def _keep_most_complete(self, df: pd.DataFrame) -> pd.DataFrame:
        columns = [c for c in self._metadata_columns if c in df.columns]
        if not columns:
            return df.drop_duplicates(subset="code_hash")
        return (
            df.assign(_filled=df[columns].notna().sum(axis=1))
            .sort_values("_filled", ascending=False, kind="stable")
            .drop_duplicates(subset="code_hash")
            .drop(columns="_filled")
            .sort_index()
        )

    @staticmethod
    def _measure_overlaps(
        frames: dict[str, pd.DataFrame],
    ) -> dict[tuple[str, str], int]:
        hashes = {n: set(df["code_hash"]) for n, df in frames.items()}
        return {(a, b): len(hashes[a] & hashes[b]) for a, b in itertools.combinations(frames, 2)}

    @staticmethod
    def _drop_cross(
        frames: dict[str, pd.DataFrame], report: DedupeReport
    ) -> dict[str, pd.DataFrame]:
        seen: set[str] = set()
        kept = {}
        for name, df in frames.items():
            unique = df[~df["code_hash"].isin(seen)]
            report.stats[name].cross = len(df) - len(unique)
            seen.update(unique["code_hash"])
            kept[name] = unique
        return kept


class ParquetRepository:
    def __init__(
        self,
        directory: Path,
        priority: tuple[str, ...],
        excluded_name_parts: tuple[str, ...],
    ):
        self._directory = directory
        self._priority = priority
        self._excluded = excluded_name_parts

    def _rank(self, name: str) -> tuple[int, str]:
        index = self._priority.index(name) if name in self._priority else len(self._priority)
        return index, name

    def _discover(self) -> list[str]:
        names = [
            p.stem
            for p in self._directory.glob("*.parquet")
            if not any(part in p.name for part in self._excluded)
        ]
        if not names:
            raise FileNotFoundError(f"No parquet datasets found in {self._directory}")
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
            "# Dedupe v0 report",
            "",
            "| " + " | ".join(REPORT_HEADERS) + " |",
            "| " + " | ".join("---" for _ in REPORT_HEADERS) + " |",
        ]
        for name, s in report.stats.items():
            lines.append(
                f"| {name} | {s.original:,} | {s.filtered:,} | {s.empty:,} | {s.conflicts:,} "
                f"| {s.internal:,} | {s.cross:,} | {s.final:,} |"
            )
        lines += ["", "## Language values removed by the language filter", ""]
        for name, s in report.stats.items():
            if s.filtered_languages:
                lines.append(f"- {name}: {s.filtered_languages}")
        lines += [
            "",
            f"Conflicting hash groups (same code, different label): {report.conflict_groups:,}",
            "",
            "## Overlap between datasets (shared normalized hashes)",
            "",
            "| dataset A | dataset B | shared |",
            "| --- | --- | --- |",
        ]
        for (a, b), count in report.overlaps.items():
            lines.append(f"| {a} | {b} | {count:,} |")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class DedupeRunner:
    def __init__(
        self,
        repository: DatasetRepository,
        engine: DedupeEngine,
        report_writer: ReportWriter,
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
    c_style = CStyleCommentRemover()
    removers_by_extension: dict[str, CommentRemover] = {
        ".py": PythonCommentRemover(),
        ".c": c_style,
        ".h": c_style,
        ".cc": c_style,
        ".cpp": c_style,
        ".cxx": c_style,
        ".hpp": c_style,
        ".java": c_style,
    }
    normalizers: dict[str, Normalizer] = {}
    for spec in specs:
        remover = next(
            (removers_by_extension[e] for e in spec.extensions if e in removers_by_extension),
            None,
        )
        if remover is not None:
            normalizers[spec.name] = StrippingNormalizer(remover)
    return normalizers


def build_default_runner(languages: frozenset[str] | None = None) -> DedupeRunner:
    selected = languages if languages is not None else frozenset(registry.enabled_languages())
    engine = DedupeEngine(
        normalizers=build_normalizers(registry.all_languages()),
        fallback=StrippingNormalizer(NoCommentRemover()),
        hasher=Sha256Hasher(),
        metadata_columns=METADATA_COLUMNS,
        languages=selected,
    )
    return DedupeRunner(
        repository=ParquetRepository(
            PROJECT_ROOT / "data" / "interim", PRIORITY_ORDER, EXCLUDED_NAME_PARTS
        ),
        engine=engine,
        report_writer=MarkdownReportWriter(PROJECT_ROOT / "docs" / "dedupe_report.md"),
    )


if __name__ == "__main__":
    build_default_runner().run()
