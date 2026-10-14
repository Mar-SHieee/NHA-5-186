"""Unified dataset schema (W1-P1-01).

The schema consists of 10 standardized columns.
"""

from __future__ import annotations

import re

import pandas as pd

from languages import registry
from languages.registry import UnknownLanguageError

SCHEMA_VERSION = "1.1"  # 1.1: added `date` and `cve`

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
    "cve": "string",  # CVE identifier, e.g. "CVE-2015-8467". <NA> if unknown
    "fixed_code": "string",  # Fixed version of the code. <NA> if unknown
    "source": "string",  # dataset name, e.g. "megavul"
}

REQUIRED_NON_NULL = ["code", "language", "label", "source"]
_CWE_RE = re.compile(r"^CWE-\d+$")  # Checks that CWE is in the format CWE-119
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")  # ISO date, e.g. 2015-12-07
_CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$")  # e.g. CVE-2015-8467
_CVE_FIND_RE = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)


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


def normalize_cve(value):
    """Return an upper-case CVE id like 'CVE-2015-8467', or <NA> if none is found."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return pd.NA
    match = _CVE_FIND_RE.search(str(value))
    return match.group(0).upper() if match else pd.NA


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
    out["language"] = out["language"].map(to_registry_language)
    out["date"] = normalize_dates(out["date"])
    out["cve"] = out["cve"].map(normalize_cve)
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

    # cve: optional, but if present must look like CVE-YYYY-NNNN+
    cves = df["cve"].dropna()
    bad_cve = int((~cves.str.fullmatch(_CVE_RE.pattern)).sum())
    if bad_cve:
        problems.append(f"cve: {bad_cve} malformed values (expected CVE-YYYY-NNNN)")

    for cwes in df["cwe"]:
        if not isinstance(cwes, list):
            problems.append("cwe values must be lists")
            continue

        for cwe in cwes:
            if not _CWE_RE.fullmatch(cwe):
                problems.append(f"malformed CWE value: {cwe}")
    return problems
