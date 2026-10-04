from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal, Optional

SCHEMA_VERSION = "1.0"
FIX_STATUS = Literal["ok", "no_fix_available", "rejected", "error"]
FIX_METHOD = Literal["template", "codet5"]
_ENABLED_LANGUAGES = ["python", "cpp"]


class _Serializable:
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
# Each step is one line where the dangerous data passes through.
class TaintStep(_Serializable):
    file: str
    line: int
    code: str = ""


@dataclass
# It strings the steps together and says where the data started and where it ended up.
class TaintPath(_Serializable):
    source: str
    sink: str
    steps: list[TaintStep] = field(default_factory=list)
    sanitizer_present: bool = False


@dataclass
# It packages the vulnerability type, location and confidence, and attaches the evidence.
class Finding(_Serializable):
    cwe: str
    confidence: float
    language: str
    file: Optional[str] = None
    function: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    taint_paths: list[TaintPath] = field(default_factory=list)


@dataclass
# If you scan the file with predict(code, "python"), you get this back.
class Result(_Serializable):
    vulnerable: bool
    cwe: Optional[str]
    confidence: float
    findings: list[Finding] = field(default_factory=list)
    taintPaths: list[TaintPath] = field(default_factory=list)
    model_version: str = "stub"
    schema_version: str = SCHEMA_VERSION


@dataclass
# the answer to one scan_repo() call
class RepoResult(_Serializable):
    files: dict[str, Result] = field(default_factory=dict)
    cwe_distribution: dict[str, int] = field(default_factory=dict)
    top_risks: list[Finding] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION


@dataclass
# did the proposed fix pass the checks?
class VerificationReport(_Serializable):
    syntax_ok: bool
    tests_ok: Optional[bool]
    redetect_ok: bool
    verdict: str  # "PASS" | "FAIL"
    notes: str = ""


@dataclass
# the answer to one suggest_fix() call
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
    return Result(vulnerable=False, cwe=None, confidence=0)


def scan_repo(path: str) -> RepoResult:
    return RepoResult()


def suggest_fix(finding: Finding) -> FixResult:
    return FixResult(
        finding=finding,
        status="no_fix_available",
        method="template",
        message="fix generation not available yet",
    )


def _check_language(language: str) -> None:
    # from shield_core.languages.registry import enabled_languages
    if language not in _ENABLED_LANGUAGES:
        raise ValueError(f"unsupported language {language}")


"""
Answer json of Result dataclass.
    {
      "vulnerable": true,
      "cwe": "CWE-89",
      "confidence": 0.91,
      "findings": [
        {
          "cwe": "CWE-89",
          "confidence": 0.91,
          "language": "python",
          "file": "app.py",
          "function": "get_user",
          "start_line": 4,
          "end_line": 8,
          "taint_paths": [
            {
              "source": "request.args",
              "sink": "cursor.execute",
              "sanitizer_present": false,
              "steps": [
                {"file": "app.py", "line": 5, "code": "user_id = request.args[\"id\"]"},
                {"file": "app.py", "line": 6, "code": "query = \"SELECT ... \" + user_id"},
                {"file": "app.py", "line": 7, "code": "cursor.execute(query)"}
              ]
            }
          ]
        }
      ],
      "model_version": "v4-fusion-1.0",
      "schema_version": "1.0"
    }
"""
