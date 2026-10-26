"""CVEfixes (C/C++) loader: CVEfixes CSV tables -> unified schema, function level.

One row = one function (method_change). For every old function
(before_change == True) we build two samples:
* old function -> label 1, fixed_code = its patched version if found
* patched function -> label 0, with empty cve, cwe, and fixed_code

CVE/CWE annotations joined to functions are commit-level associations; they do
not prove that every associated CVE/CWE affects every changed function.
The complete commit-CVE relation is preserved in a separate mapping parquet.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from shield_core.datasets.project_names import project_from_repo_url
from shield_core.datasets.schema import conform, to_parquet, validate

log = logging.getLogger(__name__)

# <this file> -> c_cpp_loaders -> datasets -> shield_core -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]

CWE_SEPARATOR = ", "
_CWE_OK = re.compile(r"^CWE-\d+$")
_CVE_OK = re.compile(r"^CVE-\d{4}-\d{4,}$")


class CVEfixesCppLoader:
    """Turns the extracted CVEfixes CSV tables into the unified schema."""

    SOURCE = "cvefixes_cpp"
    MAPPING_NAME = "cvefixes_cpp_commit_cve_mapping.parquet"
    LANGUAGE_MAP = {"c": "c", "c++": "cpp"}

    TABLE_COLUMNS = {
        "method_change": ["file_change_id", "signature", "code", "before_change"],
        "file_change": ["file_change_id", "hash", "programming_language"],
        "commits": ["hash", "repo_url", "author_date"],
        "fixes": ["cve_id", "hash"],
        "cwe_classification": ["cve_id", "cwe_id"],
    }

    COLUMN_MAP = {
        "hash": "commit",
        "programming_language": "language",
        "repo_url": "project",
        "author_date": "date",
    }

    # ---------- setup and reading ----------

    def __init__(self, raw_dir: Path | None = None, interim_dir: Path | None = None) -> None:
        self.raw_dir = Path(raw_dir) if raw_dir else PROJECT_ROOT / "data" / "raw" / "cvefixes_cpp"
        self.interim_dir = Path(interim_dir) if interim_dir else PROJECT_ROOT / "data" / "interim"

    def _load_single_csv(self, table_name: str) -> pd.DataFrame:
        """Read one CVEfixes table, keeping only the columns we need."""
        path = self.raw_dir / f"{table_name}.csv"
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found. Run: python -m "
                "shield_core.datasets.cvefixes_build.cvefixes_cpp_tables_extraction"
            )
        return pd.read_csv(path, usecols=self.TABLE_COLUMNS[table_name])

    def _load_tables(self) -> dict[str, pd.DataFrame]:
        """Read all the tables the loader needs."""
        return {name: self._load_single_csv(name) for name in self.TABLE_COLUMNS}

    # ---------- small helpers ----------

    @staticmethod
    def _to_bool(series: pd.Series) -> pd.Series:
        """True/False as bool or as text ('True', 'false', ...) -> bool."""
        return series.astype(str).str.strip().str.lower().eq("true")

    @staticmethod
    def _has_text(series: pd.Series) -> pd.Series:
        """True where the value is not missing and not only whitespace."""
        return series.notna() & (series.astype(str).str.strip() != "")

    @staticmethod
    def _join_cwe(ids: pd.Series) -> str:
        """Unique CWE ids sorted by number, joined: 'CWE-20, CWE-79'."""
        unique = sorted(set(ids), key=lambda cwe: int(cwe.split("-")[1]))
        return CWE_SEPARATOR.join(unique)

    @staticmethod
    def _cve_sort_key(cve: str) -> tuple[int, int]:
        """Sort CVE IDs by year and numeric suffix."""
        _, year, number = cve.split("-")
        return int(year), int(number)

    # ---------- merging the tables ----------

    def _pair_old_with_new(self, method_change: pd.DataFrame) -> pd.DataFrame:
        """Old functions (before_change True) next to their patched version.

        Returns file_change_id, code (old) and fixed_code (patched, NA if no match).
        """
        is_old = self._to_bool(method_change["before_change"])
        keys = ["file_change_id", "signature"]
        old = method_change.loc[is_old, keys + ["code"]]
        new = (
            method_change.loc[~is_old, keys + ["code"]]
            .rename(columns={"code": "fixed_code"})
            .drop_duplicates(subset=keys)
        )
        return old.merge(new, on=keys, how="left").drop(columns="signature")

    def _aggregate_cwe_per_commit(
        self, fixes: pd.DataFrame, cwe_classification: pd.DataFrame
    ) -> pd.DataFrame:
        """One row per commit hash with all its valid CWE ids in one string."""
        valid = cwe_classification[
            cwe_classification["cwe_id"].astype(str).str.fullmatch(_CWE_OK)
        ].drop_duplicates(["cve_id", "cwe_id"])
        joined = fixes[["cve_id", "hash"]].dropna().merge(valid, on="cve_id", how="inner")
        if joined.empty:
            return pd.DataFrame(columns=["hash", "cwe"])
        return joined.groupby("hash")["cwe_id"].agg(self._join_cwe).rename("cwe").reset_index()

    def _aggregate_cve_per_commit(self, fixes: pd.DataFrame) -> pd.DataFrame:
        """Collect every valid CVE associated with each commit as a sorted list.

        These are commit-level associations, not proof that every CVE affects
        every function changed by that commit. The full mapping is saved separately.
        """
        valid = fixes.dropna(subset=["hash", "cve_id"]).copy()
        valid["cve_id"] = valid["cve_id"].astype("string").str.strip().str.upper()
        valid = valid[valid["cve_id"].str.fullmatch(_CVE_OK).fillna(False)]
        if valid.empty:
            return pd.DataFrame(columns=["hash", "cve"])
        return (
            valid.groupby("hash")["cve_id"]
            .agg(lambda ids: sorted(set(ids), key=self._cve_sort_key))
            .rename("cve")
            .reset_index()
        )

    def _save_commit_cve_mapping(self, fixes: pd.DataFrame) -> Path:
        """Preserve every distinct commit-CVE association without duplicating code rows."""
        mapping = (
            fixes[["hash", "cve_id"]]
            .dropna(subset=["hash", "cve_id"])
            .rename(columns={"hash": "commit", "cve_id": "cve"})
        )
        mapping["commit"] = mapping["commit"].astype("string").str.strip()
        mapping["cve"] = mapping["cve"].astype("string").str.strip().str.upper()
        mapping = (
            mapping[mapping["commit"].ne("") & mapping["cve"].str.fullmatch(_CVE_OK).fillna(False)]
            .drop_duplicates()
            .reset_index(drop=True)
        )

        self.interim_dir.mkdir(parents=True, exist_ok=True)
        path = self.interim_dir / self.MAPPING_NAME
        mapping.to_parquet(path, index=False)
        log.info("saved %s (%d commit-CVE links)", path, len(mapping))
        return path

    def _prepare_commits(self, commits: pd.DataFrame) -> pd.DataFrame:
        """One row per hash (the same commit can appear under forked repos)."""
        return commits.drop_duplicates(subset="hash")[["hash", "repo_url", "author_date"]]

    def _merge_tables(self, tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Join function pairs with commit metadata, CVEs, and CWEs."""
        pairs = self._pair_old_with_new(tables["method_change"])
        commits = self._prepare_commits(tables["commits"])
        cwe = self._aggregate_cwe_per_commit(tables["fixes"], tables["cwe_classification"])
        cve = self._aggregate_cve_per_commit(tables["fixes"])
        return (
            pairs.merge(
                tables["file_change"],
                on="file_change_id",
                how="inner",
                validate="many_to_one",
            )
            .merge(commits, on="hash", how="left", validate="many_to_one")
            .merge(cwe, on="hash", how="left", validate="many_to_one")
            .merge(cve, on="hash", how="left", validate="many_to_one")
        )

    # ---------- cleaning ----------

    def _blank_identical_fixes(self, df: pd.DataFrame) -> pd.DataFrame:
        """Patched code equal to old code is not a fix: set fixed_code to NA."""
        out = df.copy()
        same = out["code"].eq(out["fixed_code"]).fillna(False)
        out.loc[same, "fixed_code"] = pd.NA
        return out

    def _rename_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """CVEfixes column names -> schema names."""
        return df.rename(columns=self.COLUMN_MAP)

    def _clean_project_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """Repo URL -> project name in the shared `owner/repo` convention."""
        out = df.copy()
        out["project"] = out["project"].map(project_from_repo_url)
        return out

    def _filter_c_cpp_only(self, df: pd.DataFrame) -> pd.DataFrame:
        """Keep C and C++ rows only."""
        languages = df["language"].astype(str).str.strip().str.lower()
        return df[languages.isin(self.LANGUAGE_MAP)].reset_index(drop=True)

    def _normalize_language(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize schema language values to 'c' or 'cpp'."""
        out = df.copy()
        out["language"] = out["language"].astype(str).str.strip().str.lower().map(self.LANGUAGE_MAP)
        return out

    def _drop_empty_code(self, df: pd.DataFrame) -> pd.DataFrame:
        """Drop rows whose code is missing or only whitespace."""
        before = len(df)
        out = df[self._has_text(df["code"])].reset_index(drop=True)
        log.info("%s: dropped %d rows with empty code", self.SOURCE, before - len(out))
        return out

    # ---------- samples ----------

    def _create_vulnerable_samples(self, df: pd.DataFrame) -> pd.DataFrame:
        """Old functions with label 1."""
        out = df.copy()
        out["label"] = 1
        return out

    def _create_safe_samples(self, df: pd.DataFrame) -> pd.DataFrame:
        """Patched functions become safe samples with no CVE/CWE annotation."""
        safe = df[self._has_text(df["fixed_code"])].copy()
        safe["code"] = safe["fixed_code"]
        safe["fixed_code"] = pd.NA
        # Preserve commit-level links in the separate mapping file, not on safe samples.
        safe["cwe"] = pd.NA
        safe["cve"] = pd.NA
        safe["label"] = 0
        return safe.reset_index(drop=True)

    def _concat_samples(self, vulnerable: pd.DataFrame, safe: pd.DataFrame) -> pd.DataFrame:
        """Stack vulnerable and safe samples."""
        return pd.concat([vulnerable, safe], ignore_index=True)

    # ---------- schema, logs, saving ----------

    def _apply_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        return conform(df, self.SOURCE)

    def _validate_schema(self, df: pd.DataFrame) -> None:
        problems = validate(df)
        if problems:
            raise ValueError(f"{self.SOURCE} failed validation: {problems}")

    def _print_logs(self, df: pd.DataFrame) -> None:
        log.info("%s: %d rows", self.SOURCE, len(df))
        log.info(
            "%s: %d vulnerable, %d not vulnerable",
            self.SOURCE,
            int((df["label"] == 1).sum()),
            int((df["label"] == 0).sum()),
        )
        log.info(
            "%s: rows per language: %s",
            self.SOURCE,
            df["language"].value_counts().to_dict(),
        )
        log.info(
            "%s: non-null cwe=%d project=%d commit=%d fixed_code=%d",
            self.SOURCE,
            int(df["cwe"].notna().sum()),
            int(df["project"].notna().sum()),
            int(df["commit"].notna().sum()),
            int(df["fixed_code"].notna().sum()),
        )
        log.info(
            "%s: date=%d rows_with_cve=%d",
            self.SOURCE,
            int(df["date"].notna().sum()),
            int(df["cve"].map(len).gt(0).sum()),
        )
        log.info("%s: validation passed", self.SOURCE)

    def _save_to_parquet(self, df: pd.DataFrame) -> Path:
        """Write final data with the stable schema Arrow types."""
        self.interim_dir.mkdir(parents=True, exist_ok=True)
        path = self.interim_dir / f"{self.SOURCE}.parquet"
        to_parquet(df, path)
        log.info("saved %s", path)
        return path

    def execute_pipeline(self) -> Path:
        """Run all pipeline stages and return the final parquet path."""
        tables = self._load_tables()
        self._save_commit_cve_mapping(tables["fixes"])

        df = self._merge_tables(tables)
        df = self._blank_identical_fixes(df)
        df = self._rename_columns(df)
        df = self._clean_project_names(df)
        df = self._filter_c_cpp_only(df)
        df = self._normalize_language(df)
        df = self._drop_empty_code(df)

        vulnerable = self._create_vulnerable_samples(df)
        safe = self._create_safe_samples(df)
        df = self._concat_samples(vulnerable, safe)

        df = self._apply_schema(df)
        self._validate_schema(df)
        self._print_logs(df)
        return self._save_to_parquet(df)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    CVEfixesCppLoader().execute_pipeline()


if __name__ == "__main__":
    main()
