import dataclasses
import re

import pytest

from shield_core import interface
from shield_core.paths import DOCS_API_DIR

DOC_PATH = DOCS_API_DIR / "api_contract.md"

TYPES = {
    "TaintStep": interface.TaintStep,
    "TaintPath": interface.TaintPath,
    "Finding": interface.Finding,
    "Result": interface.Result,
    "RepoResult": interface.RepoResult,
    "VerificationReport": interface.VerificationReport,
    "FixResult": interface.FixResult,
}


def _doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")


def _doc_fields(name: str) -> set[str]:
    """Field names in the first table of the '### 2.x `Name`' section of the contract."""
    section = re.search(rf"### 2\.\d+ `{name}`\n(.*?)(?=\n### |\n## |\Z)", _doc(), re.S)
    assert section, f"section for {name} not found in api_contract.md"
    table = re.search(r"(?:^\|.*\n?)+", section.group(1), re.M)  # first table only
    assert table, f"no field table found for {name}"
    return set(re.findall(r"^\| `(\w+)` \|", table.group(0), re.M))


@pytest.mark.parametrize("name", TYPES)
def test_contract_fields_match_dataclass(name):
    code_fields = {f.name for f in dataclasses.fields(TYPES[name])}
    assert _doc_fields(name) == code_fields, name


def test_contract_states_the_current_versions():
    doc = _doc()
    assert f'`schema_version = "{interface.SCHEMA_VERSION}"`' in doc
    assert interface.INTERFACE_VERSION in doc
