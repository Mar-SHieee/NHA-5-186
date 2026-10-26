"""Read-only acceptance audit for every SHIELD *_deduped.parquet dataset.

From the repository root:
    python scripts/data_audit/acceptance_check.py
    python scripts/data_audit/acceptance_check.py --data-dir data/interim \
        --report docs/datasets/audits/dataset_audit.md

Discovery follows the dedupe output naming convention. Normalization and hash
construction use the SAME classes and language registry as dedupe.py.
"""

from __future__ import annotations

import argparse
import json
import re

# Works when executed as `python scripts/data_audit/acceptance_check.py` from project root.
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Protocol

import pandas as pd

from shield_core.paths import DOCS_AUDITS_DIR, REPO_ROOT

ROOT = REPO_ROOT
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shield_core.datasets.pipeline.dedupe import (  # noqa: E402
    PRIORITY_ORDER,
    ConservativeNormalizer,
    Sha256Hasher,
    build_layoutless_normalizers,
    build_normalizers,
)
from shield_core.datasets.schema import COLUMNS, LIST_COLUMNS, validate  # noqa: E402
from shield_core.languages import registry  # noqa: E402

_WHITESPACE = re.compile(r"\s+")


class DatasetSource(Protocol):
    def discover(self) -> list[Path]: ...
    def read(self, path: Path) -> pd.DataFrame: ...


class AuditWriter(Protocol):
    def write(self, report: str) -> None: ...


class ParquetDatasetSource:
    def __init__(self, directory: Path):
        self.directory = directory

    def discover(self) -> list[Path]:
        if not self.directory.is_dir():
            raise FileNotFoundError(f"Data directory not found: {self.directory}")
        files = sorted(self.directory.glob("*_deduped.parquet"))
        if not files:
            raise FileNotFoundError(f"No *_deduped.parquet files found in {self.directory}")
        return files

    def missing_expected(self, expected: tuple[str, ...]) -> list[str]:
        """Datasets dedupe.py is supposed to produce that have no *_deduped.parquet."""
        return [n for n in expected if not (self.directory / f"{n}_deduped.parquet").exists()]

    def read(self, path: Path) -> pd.DataFrame:
        return pd.read_parquet(path)


class MarkdownWriter:
    def __init__(self, path: Path):
        self.path = path

    def write(self, report: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(report, encoding="utf-8")


class DedupeCompatibleHasher:
    """Identical hash key to DedupeEngine._with_hash (including language prefix)."""

    def __init__(self):
        self.normalizers = build_normalizers(registry.all_languages())
        self.fallback = ConservativeNormalizer()
        self.hasher = Sha256Hasher()
        self.layoutless = build_layoutless_normalizers(registry.all_languages())

    def loose_keys(self, code: object, language: object) -> tuple[str, str, bool] | None:
        """Layout-insensitive keys of dedupe.py (Python only): (layout key, squash key, flat?)."""
        lang = str(language)
        normalizer = self.layoutless.get(lang)
        if normalizer is None or not isinstance(code, str) or not code.strip():
            return None
        text = normalizer.normalize(code)
        layout = self.hasher.hash("layout\0" + lang + "\0" + text) if text else ""
        squash = self.hasher.hash("squash\0" + lang + "\0" + _WHITESPACE.sub("", code))
        return layout, squash, "\n" not in code.replace("\r\n", "\n").strip()

    def hash(self, code: object, language: object) -> str:
        if not isinstance(code, str) or not code.strip():
            return ""
        lang = str(language)
        normalized = self.normalizers.get(lang, self.fallback).normalize(code)
        return self.hasher.hash(lang + "\0" + normalized) if normalized else ""

    def hashes(self, df: pd.DataFrame) -> pd.Series:
        if not {"code", "language"}.issubset(df.columns):
            return pd.Series("", index=df.index, dtype="string")
        return pd.Series(
            [
                self.hash(code, language)
                for code, language in zip(df["code"], df["language"], strict=True)
            ],
            index=df.index,
            dtype="string",
        )


def cwe_values(value: object) -> list[str]:
    """Handle parquet-decoded numpy arrays without changing stored data."""
    if value is None or value is pd.NA:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (list, tuple, set)):
        return [str(x) for x in value if x is not None and x is not pd.NA]
    return [str(value)]


@dataclass
class DatasetAudit:
    name: str
    rows: int
    columns: int
    missing: dict[str, int]
    empty_strings: dict[str, int]
    label_counts: dict[str, int]
    language_counts: dict[str, int]
    unique_hashes: int
    duplicate_hash_rows: int
    empty_code_rows: int
    schema_errors: list[str]
    cwe_counts: Counter
    vulnerable_cwe_counts: Counter
    multi_cwe_rows: int
    hashes: set[str]
    hash_labels: dict[str, set[str]]
    missing_commits: int | None
    empty_lists: dict[str, int]
    # layout-insensitive key -> strict hashes of rows WITHOUT / WITH line breaks (Python only)
    flat_loose: dict[str, set[str]]
    laid_loose: dict[str, set[str]]

    @property
    def preliminary_pass(self) -> bool:
        return (
            not self.schema_errors and self.duplicate_hash_rows == 0 and self.empty_code_rows == 0
        )


class DatasetAuditor:
    def __init__(self, hasher: DedupeCompatibleHasher):
        self.hasher = hasher

    def inspect(self, name: str, df: pd.DataFrame) -> DatasetAudit:
        errors: list[str] = []
        if list(df.columns) != COLUMNS:
            errors.append(f"columns differ from schema.COLUMNS: {list(df.columns)}")
        if set(COLUMNS).issubset(df.columns):
            # Parquet converts list columns (cwe AND cve) to ndarray; schema.validate expects
            # lists. Convert on a temporary copy ONLY; never rewrite or re-conform data.
            check = df.copy()
            for col in LIST_COLUMNS:
                check[col] = check[col].map(cwe_values)
            try:
                errors.extend(validate(check))
            except (TypeError, ValueError) as exc:
                errors.append(f"schema.validate raised {type(exc).__name__}: {exc}")
        else:
            errors.append(f"missing schema columns: {sorted(set(COLUMNS) - set(df.columns))}")

        missing = {str(col): int(df[col].isna().sum()) for col in df.columns}
        # List columns are never NA; "missing" for them means an empty list.
        empty_lists = {
            col: int(df[col].map(lambda v: not cwe_values(v)).sum())
            for col in LIST_COLUMNS
            if col in df.columns
        }
        empty_strings = {}
        for col in df.columns:
            if pd.api.types.is_string_dtype(df[col]) or pd.api.types.is_object_dtype(df[col]):
                # Object array columns cannot be cast safely to strings for this check.
                if col == "cwe":
                    continue
                empty_strings[str(col)] = int(
                    df[col].map(lambda x: isinstance(x, str) and not x.strip()).sum()
                )

        labels = df["label"].astype("string") if "label" in df else pd.Series(dtype="string")
        languages = (
            df["language"].astype("string") if "language" in df else pd.Series(dtype="string")
        )
        hashes = self.hasher.hashes(df)
        valid_hashes = hashes[hashes.ne("")]
        hash_labels: dict[str, set[str]] = defaultdict(set)
        if "label" in df:
            for h, label in zip(hashes, labels, strict=True):
                if h:
                    hash_labels[h].add(str(label))

        flat_loose: dict[str, set[str]] = defaultdict(set)
        laid_loose: dict[str, set[str]] = defaultdict(set)
        if {"code", "language"}.issubset(df.columns):
            for h, code, language in zip(hashes, df["code"], df["language"], strict=True):
                keys = self.hasher.loose_keys(code, language) if h else None
                if keys is None:
                    continue
                layout, squash, is_flat = keys
                target = flat_loose if is_flat else laid_loose
                for key in (layout, squash):
                    if key:
                        target[key].add(h)

        total_cwe = Counter()
        vuln_cwe = Counter()
        multi = 0
        if "cwe" in df:
            for i, raw_cwe in enumerate(df["cwe"]):
                values = set(cwe_values(raw_cwe))
                if len(values) > 1:
                    multi += 1
                if not values:
                    values = {"<MISSING>"}
                lang = str(languages.iloc[i]) if i < len(languages) else "<MISSING>"
                for cwe in values:
                    total_cwe[(lang, cwe)] += 1
                    if i < len(labels) and labels.iloc[i] == "1":
                        vuln_cwe[(lang, cwe)] += 1

        return DatasetAudit(
            name=name,
            rows=len(df),
            columns=len(df.columns),
            missing=missing,
            empty_strings=empty_strings,
            label_counts={
                str(k): int(v) for k, v in labels.fillna("<NULL>").value_counts().items()
            },
            language_counts={
                str(k): int(v) for k, v in languages.fillna("<NULL>").value_counts().items()
            },
            unique_hashes=int(valid_hashes.nunique()),
            duplicate_hash_rows=int(valid_hashes.duplicated(keep=False).sum()),
            empty_code_rows=int(hashes.eq("").sum()),
            schema_errors=errors,
            cwe_counts=total_cwe,
            vulnerable_cwe_counts=vuln_cwe,
            multi_cwe_rows=multi,
            hashes=set(valid_hashes.tolist()),
            hash_labels=dict(hash_labels),
            missing_commits=missing.get("commit"),
            empty_lists=empty_lists,
            flat_loose=dict(flat_loose),
            laid_loose=dict(laid_loose),
        )


class AcceptanceRunner:
    def __init__(self, source: DatasetSource, auditor: DatasetAuditor, writer: AuditWriter):
        self.source = source
        self.auditor = auditor
        self.writer = writer

    def run(self) -> list[DatasetAudit]:
        audits = []
        for path in self.source.discover():
            name = path.name.removesuffix("_deduped.parquet")
            print(f"[AUDIT] {name}: {path}", flush=True)
            audit = self.auditor.inspect(name, self.source.read(path))
            audits.append(audit)
            print(
                f"  rows={audit.rows:,} unique_hashes={audit.unique_hashes:,} "
                f"duplicate_rows={audit.duplicate_hash_rows:,} "
                f"verdict={'PRELIMINARY PASS' if audit.preliminary_pass else 'REVIEW'}",
                flush=True,
            )
        missing_expected = self.source.missing_expected(PRIORITY_ORDER)
        if missing_expected:
            print(f"[WARNING] No *_deduped.parquet for: {missing_expected}", flush=True)
        report = self.render(audits, missing_expected)
        self.writer.write(report)
        return audits

    @staticmethod
    def residual_layout_matches(audits: list[DatasetAudit]) -> tuple[int, int]:
        """Flattened Python code (no line breaks) that still matches a laid-out copy.

        Returns (unambiguous, ambiguous) counts of distinct flattened code variants.
        Unambiguous = exactly one laid-out version matches, so dedupe.py should have linked
        them (expected 0). Ambiguous = several laid-out versions match; dedupe leaves those.
        """
        flat: dict[str, set[str]] = defaultdict(set)
        laid: dict[str, set[str]] = defaultdict(set)
        for a in audits:
            for key, hashes in a.flat_loose.items():
                flat[key] |= hashes
            for key, hashes in a.laid_loose.items():
                laid[key] |= hashes
        unambiguous: set[str] = set()
        ambiguous: set[str] = set()
        for key, flat_hashes in flat.items():
            versions = laid.get(key, set())
            if len(versions) == 1:
                unambiguous |= flat_hashes
            elif len(versions) > 1:
                ambiguous |= flat_hashes
        return len(unambiguous), len(ambiguous - unambiguous)

    @staticmethod
    def render(audits: list[DatasetAudit], missing_expected: list[str] | None = None) -> str:
        lines = [
            "# SHIELD Dataset Acceptance Audit",
            "",
            f"Generated (UTC): {datetime.now(timezone.utc).isoformat()}",
            "",
            "Scope: every `*_deduped.parquet` file discovered in the configured directory.",
            "This is a read-only, preliminary automated audit, not final ML acceptance.",
            "",
            "## Dataset summary",
            "",
            (
                "| Dataset | Rows | Columns | Unique hashes | Duplicate-hash "
                "rows | Empty code | Multi-CWE rows | Missing commits | Verdict |"
            ),
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
        for a in audits:
            verdict = "PRELIMINARY PASS" if a.preliminary_pass else "REVIEW"
            lines.append(
                f"| {a.name} | {a.rows:,} | {a.columns} | {a.unique_hashes:,} | "
                f"{a.duplicate_hash_rows:,} | {a.empty_code_rows:,} | {a.multi_cwe_rows:,} | "
                f"{a.missing_commits if a.missing_commits is not None else 'N/A'} | {verdict} |"
            )
        lines += ["", "## Schema, nulls, labels and languages", ""]
        for a in audits:
            lines += [
                f"### {a.name}",
                "",
                f"- Schema errors: `{json.dumps(a.schema_errors, ensure_ascii=False)}`",
                f"- Missing values: `{json.dumps(a.missing, ensure_ascii=False)}`",
                f"- Empty lists (cwe / cve): `{json.dumps(a.empty_lists, ensure_ascii=False)}`",
                (
                    f"- Empty strings (non-CWE columns): "
                    f"`{json.dumps(a.empty_strings, ensure_ascii=False)}`"
                ),
                f"- Label distribution: `{json.dumps(a.label_counts, ensure_ascii=False)}`",
                f"- Language distribution: `{json.dumps(a.language_counts, ensure_ascii=False)}`",
                "",
            ]
        lines += [
            "## Language × CWE matrix",
            "",
            "Multi-CWE rows count once in each CWE category. `<MISSING>` denotes empty CWE lists.",
            "",
            "| Dataset | Language | CWE | Samples | Vulnerable samples |",
            "| --- | --- | --- | ---: | ---: |",
        ]
        for a in audits:
            for (lang, cwe), count in sorted(
                a.cwe_counts.items(),
                key=lambda kv: (kv[0][0], -a.vulnerable_cwe_counts[kv[0]], kv[0][1]),
            ):
                lines.append(
                    f"| {a.name} | {lang} | {cwe} | {count:,} | "
                    f"{a.vulnerable_cwe_counts[(lang, cwe)]:,} |"
                )
        lines += [
            "",
            "## Cross-dataset code overlap",
            "",
            "| Dataset A | Dataset B | Shared normalized hashes |",
            "| --- | --- | ---: |",
        ]
        for left, right in combinations(audits, 2):
            lines.append(f"| {left.name} | {right.name} | {len(left.hashes & right.hashes):,} |")
        all_labels: dict[str, set[str]] = defaultdict(set)
        for a in audits:
            for h, labels in a.hash_labels.items():
                all_labels[h].update(labels)
        conflicts = sum(len(labels) > 1 for labels in all_labels.values())
        unambiguous, ambiguous = AcceptanceRunner.residual_layout_matches(audits)
        lines += [
            "",
            "## Expected datasets and layout-insensitive matches",
            "",
            (
                "- Datasets expected by `dedupe.PRIORITY_ORDER` with no `*_deduped.parquet`: "
                f"**{', '.join(missing_expected) if missing_expected else 'none'}**."
            ),
            (
                "- Python code without line breaks that still matches exactly one laid-out copy: "
                f"**{unambiguous:,}** (expected 0; anything else means dedupe missed a duplicate)."
            ),
            (
                "- Python code without line breaks that matches several different laid-out "
                f"versions (left alone on purpose): {ambiguous:,}."
            ),
            "",
            "## Label conflicts and limitations",
            "",
            f"- Remaining cross-dataset normalized-hash label-conflict groups: **{conflicts:,}**.",
            (
                "- Hashes use the same language-prefix, "
                "normalizers and SHA-256 implementation as `dedupe.py`."
            ),
            (
                "- CWE and CVE arrays decoded from Parquet are "
                "converted to Python lists only for `schema.validate()`."
            ),
            (
                "- No CVE/commit/project group-aware "
                "splitting or semantic-clone detection is performed."
            ),
            "- A PRELIMINARY PASS only covers schema, empty-code and duplicate-hash checks.",
            (
                "- This audit does not validate that commit SHAs "
                "correspond to security fixes or that CWE labels are correct."
            ),
            "- No dataset files are modified.",
            "",
        ]
        return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "interim")
    parser.add_argument("--report", type=Path, default=DOCS_AUDITS_DIR / "dataset_audit.md")
    args = parser.parse_args()
    runner = AcceptanceRunner(
        ParquetDatasetSource(args.data_dir),
        DatasetAuditor(DedupeCompatibleHasher()),
        MarkdownWriter(args.report),
    )
    audits = runner.run()
    print(f"[DONE] Audited {len(audits)} datasets. Report: {args.report}")
    if any(not a.preliminary_pass for a in audits):
        print("[WARNING] Some datasets need review; inspect the report.")


if __name__ == "__main__":
    main()
