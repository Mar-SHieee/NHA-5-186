"""Unified dataset schema (W1-P1-01)."""

from __future__ import annotations

import re

import pandas as pd

SCHEMA_VERSION = "1.0"

COLUMNS = [
    "code",
    "language",
    "label",
    "cwe",
    "project",
    "commit",
    "date",
    "fixed_code",
    "source",
]

DTYPES = {
    "code": "string",  #  source code
    "language": "string",  # "python" | "cpp"
    "label": "int8",  # 1 = vulnerable, 0 = not vulnerable
    "cwe": "string",  # Vulnerability type: "CWE-119" or <NA>
    "project": "string",  # Project name, e.g. "linux" or "openssl". <NA> if unknown
    "commit": "string",  # Commit hash, e.g. "a1b2c3d4". <NA> if unknown
    "date": "datetime64[ns]",  # Date of the commit. <NA> if unknown
    "fixed_code": "string",  # Fixed version of the code. <NA> if unknown
    "source": "string",  # dataset name, e.g. "megavul"
}

REQUIRED_NON_NULL = ["code", "language", "label", "source"]
_CWE_RE = re.compile(r"^CWE-\d+$")  # Checks that CWE is in the format CWE-119


def normalize_cwe(value) -> str | None:
    """'119', 'CWE-119', 'cwe119' -> 'CWE-119'. Unknown or NVD placeholders -> None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    m = re.search(r"(\d+)", str(value))
    return f"CWE-{int(m.group(1))}" if m else None


def conform(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Force a loader's output into the unified schema."""
    out = df.copy()
    out["source"] = source
    for col in COLUMNS:
        if col not in out:
            out[col] = pd.NA
    out["cwe"] = out["cwe"].map(normalize_cwe)
    out["date"] = pd.to_datetime(
        out["date"], errors="coerce", utc=True, format="mixed"
    ).dt.tz_localize(None)
    out = out[COLUMNS].astype(DTYPES)
    return out.reset_index(drop=True)


def validate(df: pd.DataFrame) -> list[str]:
    """Return a list of problems (empty list = OK)."""
    problems = []
    if list(df.columns) != COLUMNS:
        problems.append(f"columns differ: {list(df.columns)}")
        return problems
    for col in REQUIRED_NON_NULL:
        n = int(df[col].isna().sum())
        if n:
            problems.append(f"{col}: {n} nulls")
    if not df["label"].isin([0, 1]).all():
        problems.append("label must be 0 or 1")
    if (df["code"].str.strip() == "").any():
        problems.append("empty code rows")
    bad = df["cwe"].dropna()
    bad = bad[~bad.str.match(_CWE_RE)]
    if len(bad):
        problems.append(f"{len(bad)} malformed CWE values")
    return problems
