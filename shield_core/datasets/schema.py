"""Unified dataset schema (W1-P1-01).

The schema consists of 8 standardized columns.
"""

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
    "fixed_code",
    "source",
]

DTYPES = {
    "code": "string",  # source code
    "language": "string",  # "python" | "cpp"
    "label": "int8",  # 1 = vulnerable, 0 = not vulnerable
    "cwe": "object",  # Vulnerability type list: ["CWE-119", ...]
    "project": "string",  # Project name, e.g. "linux" or "openssl". <NA> if unknown
    "commit": "string",  # Commit hash, e.g. "a1b2c3d4". <NA> if unknown
    "fixed_code": "string",  # Fixed version of the code. <NA> if unknown
    "source": "string",  # dataset name, e.g. "megavul"
}

REQUIRED_NON_NULL = ["code", "language", "label", "source"]
_CWE_RE = re.compile(r"^CWE-\d+$")  # Checks that CWE is in the format CWE-119


def normalize_cwe(value) -> list[str]:
    """Normalize one or more CWE values into a list."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []

    if not isinstance(value, (list, tuple)):
        value = [value]

    result = []

    for item in value:
        if item is None:
            continue

        match = re.fullmatch(
            r"(?:CWE-)?(\d+)",
            str(item).strip(),
            re.IGNORECASE,
        )

        if match:
            result.append(f"CWE-{int(match.group(1))}")

    return result


def conform(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Force a loader's output into the unified schema."""
    out = df.copy()
    out["source"] = source
    for col in COLUMNS:
        if col not in out:
            out[col] = pd.NA
    out["cwe"] = out["cwe"].map(normalize_cwe)
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
    for cwes in df["cwe"]:
        if not isinstance(cwes, list):
            problems.append("cwe values must be lists")
            continue

        for cwe in cwes:
            if not _CWE_RE.fullmatch(cwe):
                problems.append(f"malformed CWE value: {cwe}")
    return problems
