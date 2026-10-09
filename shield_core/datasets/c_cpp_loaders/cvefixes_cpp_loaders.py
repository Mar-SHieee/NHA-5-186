"""CVEfixes (C/C++) loader: CVEfixes CSV tables -> unified schema, function level.

One row = one function (``method_change``). For every old function
(``before_change == True``) we build two samples:

* the old function      -> label 1, ``fixed_code`` = its patched version (if found)
* the patched function  -> label 0 (``fixed_code`` and ``cwe`` are empty)

C and C++ are loaded together (CVEfixes labels them 'C' and 'C++'); the
``language`` column keeps them apart as 'c' and 'cpp'.

Known limitation: CVEfixes stores every function that changed in a fix commit,
so some "vulnerable" functions are only touched by the commit, not the bug itself.

Pairing the old and the patched function is done on ``file_change_id`` +
``signature``. Functions with no match keep ``fixed_code = NA`` and produce no
safe sample.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from shield_core.datasets.schema import conform, validate

log = logging.getLogger(__name__)

# <this file> -> c_cpp_loaders -> datasets -> shield_core -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]

CWE_SEPARATOR = ", "
_CWE_OK = re.compile(r"^CWE-\d+$")  # drops NVD-CWE-Other / NVD-CWE-noinfo


class CVEfixesCppLoader:
    """Turns the extracted CVEfixes CSV tables into the unified schema."""

    SOURCE = "cvefixes_cpp"  # value of the `source` column and the parquet name

    # CVEfixes language name (lowercase) -> schema language name
    LANGUAGE_MAP = {"c": "c", "c++": "cpp"}

    # Only the columns we need: file_change and method_change hold huge code columns.
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
                "shield_core.datasets.c_cpp_loaders.cvefixes_cpp_tables_extraction"
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
    def _project_name(url) -> str | None:
        """Repo URL -> project name (last path segment, no '.git')."""
        if pd.isna(url):
            return None
        name = str(url).strip().rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        return name or None

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
        valid = cwe_classification[cwe_classification["cwe_id"].astype(str).str.match(_CWE_OK)]
        joined = fixes[["cve_id", "hash"]].merge(valid, on="cve_id", how="inner")
        return joined.groupby("hash")["cwe_id"].agg(self._join_cwe).rename("cwe").reset_index()

    def _prepare_commits(self, commits: pd.DataFrame) -> pd.DataFrame:
        """One row per hash (the same commit can appear under forked repos)."""
        return commits.drop_duplicates(subset="hash")[["hash", "repo_url", "author_date"]]

    def _merge_tables(self, tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Join functions with their file, commit and CWE info into one table."""
        pairs = self._pair_old_with_new(tables["method_change"])
        commits = self._prepare_commits(tables["commits"])
        cwe = self._aggregate_cwe_per_commit(tables["fixes"], tables["cwe_classification"])
        return (
            pairs.merge(
                tables["file_change"], on="file_change_id", how="inner", validate="many_to_one"
            )
            .merge(commits, on="hash", how="left", validate="many_to_one")
            .merge(cwe, on="hash", how="left", validate="many_to_one")
        )

    # ---------- cleaning ----------

    def _blank_identical_fixes(self, df: pd.DataFrame) -> pd.DataFrame:
        """Patched code equal to the old code is not a fix: set fixed_code to NA."""
        out = df.copy()
        same = out["code"] == out["fixed_code"]
        out.loc[same, "fixed_code"] = pd.NA
        return out

    def _rename_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """CVEfixes column names -> schema names."""
        return df.rename(columns=self.COLUMN_MAP)

    def _clean_project_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """Repo URL -> project name."""
        out = df.copy()
        out["project"] = out["project"].map(self._project_name)
        return out

    def _filter_c_cpp_only(self, df: pd.DataFrame) -> pd.DataFrame:
        """Keep C and C++ rows only."""
        is_c_cpp = df["language"].astype(str).str.strip().str.lower().isin(self.LANGUAGE_MAP)
        return df[is_c_cpp].reset_index(drop=True)

    def _normalize_language(self, df: pd.DataFrame) -> pd.DataFrame:
        """Write the language the way the schema expects it ('c' or 'cpp')."""
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
        """Patched functions become the code, with label 0 and no CWE."""
        safe = df[self._has_text(df["fixed_code"])].copy()
        safe["code"] = safe["fixed_code"]
        safe["fixed_code"] = pd.NA
        safe["cwe"] = pd.NA
        safe["label"] = 0
        return safe.reset_index(drop=True)

    def _concat_samples(self, vulnerable: pd.DataFrame, safe: pd.DataFrame) -> pd.DataFrame:
        """Stack the vulnerable and the safe samples."""
        return pd.concat([vulnerable, safe], ignore_index=True)

    # ---------- schema, logs, saving ----------

    def _apply_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        """Force the table into the unified schema."""
        return conform(df, self.SOURCE)

    def _validate_schema(self, df: pd.DataFrame) -> None:
        """Raise if the table breaks a schema rule."""
        problems = validate(df)
        if problems:
            raise ValueError(f"{self.SOURCE} failed validation: {problems}")

    def _print_logs(self, df: pd.DataFrame) -> None:
        """Row counts that feed the acceptance audit."""
        name = self.SOURCE
        log.info("%s: %d rows", name, len(df))
        log.info(
            "%s: %d vulnerable, %d not vulnerable",
            name,
            int((df["label"] == 1).sum()),
            int((df["label"] == 0).sum()),
        )
        log.info("%s: rows per language: %s", name, df["language"].value_counts().to_dict())
        log.info(
            "%s: non-null cwe=%d project=%d commit=%d fixed_code=%d",
            name,
            df["cwe"].notna().sum(),
            df["project"].notna().sum(),
            df["commit"].notna().sum(),
            df["fixed_code"].notna().sum(),
        )
        log.info("%s: validation passed", name)

    def _save_to_parquet(self, df: pd.DataFrame) -> Path:
        """Write the final table to the interim folder."""
        self.interim_dir.mkdir(parents=True, exist_ok=True)
        path = self.interim_dir / f"{self.SOURCE}.parquet"
        df.to_parquet(path, index=False)
        log.info("saved %s", path)
        return path

    # ---------- the only method called from outside ----------

    def execute_pipeline(self) -> Path:
        """Run every step in order and return the parquet path."""
        tables = self._load_tables()
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
