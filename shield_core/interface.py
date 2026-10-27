from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, Optional

from shield_core.languages import registry
from shield_core.models import registry as model_registry

INTERFACE_VERSION = "1.0"  # covers the signatures and exceptions
SCHEMA_VERSION = "1.0"  # covers the payload fields

FIX_STATUS = Literal["ok", "no_fix_available", "rejected", "error"]
FIX_METHOD = Literal["template", "codet5"]
VERDICT = Literal["PASS", "FAIL"]


class ShieldError(Exception):
    """Base class for every error the core interface raises on purpose."""


class UnsupportedLanguageError(ShieldError, ValueError):
    """Language is unknown or disabled. HTTP 422 `unsupported_language`."""


class RepoNotFoundError(ShieldError, FileNotFoundError):
    """scan_repo() got a path that is not a directory. HTTP 404 `not_found`."""


class ModelUnavailableError(ShieldError, RuntimeError):
    """No model could be loaded, not even the V1 fallback. HTTP 503 `model_unavailable`."""


class _Serializable:
    def to_dict(self) -> dict:
        return asdict(self)


# Each step is one line where the dangerous data passes through.
@dataclass
class TaintStep(_Serializable):
    file: str
    line: int
    code: str = ""


# It strings the steps together and says where the data started and where it ended up.
@dataclass
class TaintPath(_Serializable):
    source: str
    sink: str
    steps: list[TaintStep] = field(default_factory=list)
    sanitizer_present: bool = False


# It packages the vulnerability type, location and confidence, and attaches the evidence.
@dataclass
class Finding(_Serializable):
    cwe: str
    confidence: float
    language: str
    file: Optional[str] = None
    function: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    taint_paths: list[TaintPath] = field(default_factory=list)


# If you scan the file with predict(code, "python"), you get this back.
@dataclass
class Result(_Serializable):
    vulnerable: bool
    cwe: Optional[str]
    confidence: float
    findings: list[Finding] = field(default_factory=list)
    # paths not tied to any single finding; normally empty.
    # Do not duplicate paths already listed in a finding
    taint_paths: list[TaintPath] = field(default_factory=list)
    model_version: str = "stub"
    schema_version: str = SCHEMA_VERSION


# the answer to one scan_repo() call
@dataclass
class RepoResult(_Serializable):
    files: dict[str, Result] = field(default_factory=dict)
    cwe_distribution: dict[str, int] = field(default_factory=dict)
    top_risks: list[Finding] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION


# did the proposed fix pass the checks?
@dataclass
class VerificationReport(_Serializable):
    syntax_ok: bool
    tests_ok: Optional[bool]
    redetect_ok: bool
    verdict: VERDICT  # "PASS" | "FAIL"
    notes: str = ""


# the answer to one suggest_fix() callI
@dataclass
class FixResult(_Serializable):
    finding: Finding
    status: FIX_STATUS
    method: FIX_METHOD
    candidate_fix: Optional[str] = None
    diff: Optional[str] = None
    verification: Optional[VerificationReport] = None
    message: str = ""  # human-readable reason
    schema_version: str = SCHEMA_VERSION


def predict(code: str, language: str) -> Result:
    _check_language(language)
    try:
        model = model_registry.get_model(language)
    except model_registry.ModelRegistryError as e:
        raise ModelUnavailableError(str(e)) from e
    result = model.predict(code, language)
    result.model_version = model.version  # always name the model that really answered
    return result


def scan_repo(path: str) -> RepoResult:
    if not Path(path).is_dir():
        raise RepoNotFoundError(f"{path} is not a directory")
    return RepoResult()


def suggest_fix(finding: Finding, code: Optional[str] = None) -> FixResult:
    return FixResult(
        finding=finding,
        status="no_fix_available",
        method="template",
        message="fix generation not available yet",
    )


def _check_language(language: str) -> None:
    try:
        registry.require_enabled(language)
    except registry.RegistryError as e:
        raise UnsupportedLanguageError(str(e)) from e
