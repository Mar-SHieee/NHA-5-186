"""Unified dataset schema (W1-P1-01).

The schema consists of 10 standardized columns.
"""

from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

from languages import registry
from languages.registry import UnknownLanguageError

SCHEMA_VERSION = "1.2"  # 1.2: `cve` is now list[str]; 1.1: added `date` and `cve`

COLUMNS = [
    "code",
    "language",
    "label",
    "cwe",
    "project",
    "commit",
    "date",
    "cve",
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
    "date": "string",  # CVE publish date or commit date, ISO "YYYY-MM-DD". <NA> if unknown
    "cve": "object",  # CVE id list: ["CVE-2015-8467", ...]. [] if unknown
    "fixed_code": "string",  # Fixed version of the code. <NA> if unknown
    "source": "string",  # dataset name, e.g. "megavul"
}

# List-valued columns. After a Parquet round trip these come back as numpy arrays,
# so `from_parquet` converts them back to plain Python lists.
LIST_COLUMNS = ["cwe", "cve"]

REQUIRED_NON_NULL = ["code", "language", "label", "source"]
_CWE_RE = re.compile(r"^CWE-\d+$")  # Checks that CWE is in the format CWE-119
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")  # ISO date, e.g. 2015-12-07
_CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$")  # e.g. CVE-2015-8467
_CVE_FIND_RE = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)


def _is_missing(value) -> bool:
    """True for None, pd.NA, and float NaN. Safe for lists/arrays (never calls pd.isna on them)."""
    return value is None or value is pd.NA or (isinstance(value, float) and math.isnan(value))


def normalize_cwe(value) -> list[str]:
    """Normalize one or more CWE values into a list."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []

    if isinstance(value, str):
        value = value.split(",")

    elif not isinstance(value, (list, tuple)):
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


def _cve_sort_key(cve: str) -> tuple[int, int]:
    """Numeric sort key so CVE-2015-8467 < CVE-2015-10000."""
    _, year, number = cve.split("-")
    return int(year), int(number)


def normalize_cve(value) -> list[str]:
    """Extract every CVE id from `value`.

    Accepts a string (possibly containing several ids), a list/tuple/set/ndarray of
    strings, or a missing value. Returns an upper-case, de-duplicated list sorted by
    (year, number). Returns [] if no valid CVE id is found.
    """
    if _is_missing(value):
        return []

    if isinstance(value, np.ndarray):
        value = value.tolist()

    items = value if isinstance(value, (list, tuple, set, frozenset)) else [value]

    found: set[str] = set()
    for item in items:
        if _is_missing(item):
            continue
        found.update(m.upper() for m in _CVE_FIND_RE.findall(str(item)))

    return sorted(found, key=_cve_sort_key)


def normalize_dates(series: pd.Series) -> pd.Series:
    """Parse any date/datetime-like values to ISO 'YYYY-MM-DD' strings (<NA> if unparseable)."""
    parsed = pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
    return parsed.dt.strftime("%Y-%m-%d")


def to_registry_language(value):
    if value is None or pd.isna(value):
        return pd.NA
    text = str(value).strip().lower()
    try:
        return registry.get(text).name
    except UnknownLanguageError:
        pass
    spec = registry.language_for_extension("." + text.replace("++", "pp"))
    return spec.name if spec else pd.NA


def conform(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Force a loader's output into the unified schema."""
    out = df.copy()
    out["source"] = source
    for col in COLUMNS:
        if col not in out:
            out[col] = pd.NA
    out["cwe"] = out["cwe"].map(normalize_cwe)
    out["cve"] = out["cve"].map(normalize_cve)
    out["language"] = out["language"].map(to_registry_language)
    out["date"] = normalize_dates(out["date"])
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
    known = {spec.name for spec in registry.all_languages()}
    unknown = sorted(set(df["language"].dropna()) - known)
    if unknown:
        problems.append(f"unknown languages: {unknown}")

    # date: optional, but if present must be ISO YYYY-MM-DD and a real calendar date
    dates = df["date"].dropna()
    bad_format = int((~dates.str.fullmatch(_DATE_RE.pattern)).sum())
    if bad_format:
        problems.append(f"date: {bad_format} values not in YYYY-MM-DD format")
    else:
        unparseable = int(pd.to_datetime(dates, errors="coerce", format="%Y-%m-%d").isna().sum())
        if unparseable:
            problems.append(f"date: {unparseable} values are not valid calendar dates")

    for cwes in df["cwe"]:
        if not isinstance(cwes, list):
            problems.append("cwe values must be lists")
            continue

        for cwe in cwes:
            if not _CWE_RE.fullmatch(cwe):
                problems.append(f"malformed CWE value: {cwe}")

    # cve: optional list; each id must look like CVE-YYYY-NNNN+, unique, and sorted
    for cves in df["cve"]:
        if not isinstance(cves, list):
            problems.append("cve values must be lists")
            continue

        bad = [c for c in cves if not (isinstance(c, str) and _CVE_RE.fullmatch(c))]
        for c in bad:
            problems.append(f"malformed CVE value: {c!r} (expected CVE-YYYY-NNNN)")
        if bad:
            continue
        if len(set(cves)) != len(cves):
            problems.append(f"duplicate CVE ids in {cves}")
        elif cves != sorted(cves, key=_cve_sort_key):
            problems.append(f"CVE ids not sorted in {cves}")
    return problems


# ---------------------------------------------------------------------------
# Parquet / PyArrow support
# ---------------------------------------------------------------------------


def arrow_schema():
    """Explicit Arrow schema. Needed so all-empty list columns are list<string>, not list<null>."""
    import pyarrow as pa

    return pa.schema(
        [
            ("code", pa.string()),
            ("language", pa.string()),
            ("label", pa.int8()),
            ("cwe", pa.list_(pa.string())),
            ("project", pa.string()),
            ("commit", pa.string()),
            ("date", pa.string()),
            ("cve", pa.list_(pa.string())),
            ("fixed_code", pa.string()),
            ("source", pa.string()),
        ]
    )


def to_parquet(df: pd.DataFrame, path) -> None:
    """Write a schema-conforming DataFrame to Parquet with a stable Arrow schema."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.Table.from_pandas(df[COLUMNS], schema=arrow_schema(), preserve_index=False)
    pq.write_table(table, path)


def from_parquet(path) -> pd.DataFrame:
    """Read a Parquet file written by `to_parquet`; list columns are restored as Python lists."""
    out = pd.read_parquet(path)
    for col in LIST_COLUMNS:
        out[col] = out[col].map(lambda v: list(v) if v is not None else [])
    return out[COLUMNS].astype(DTYPES)
