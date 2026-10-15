"""
`verification.notes` starts with one line listing the checks that ran, so a client can show them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from shield_core.interface import VerificationReport

EVIDENCE_PREFIX = "[evidence] "
NOT_VERIFIED_TAIL = "Not verified by re-detection."


"""
redetection will have a rating which reflects quality of the cwe detection
to avoid false pass and false fail
"""


class Rating(str, Enum):
    STRONG = "strong"
    WEAK = "weak"
    NONE = "none"


"""
Strong classes verdict will be gated by syntax,
test if found and redetection all passing
weak/none classes verdict will be gated by syntax,
tests if found and pattern and it won't be gated by redetection value
"""


@dataclass(frozen=True)
class Checks:
    syntax_ok: bool
    redetect_ok: bool
    tests_ok: Optional[bool]  # None = no tests found, check not run
    pattern_ok: Optional[bool] = None  # class-specific syntactic check; None = not run


# Check if class swe is strong to be gated by redetection
def _gated_by_redetection(rating: Rating) -> bool:
    return rating is Rating.STRONG


def decide_verdict(rating: Rating, checks: Checks) -> str:
    """Return "PASS" or "FAIL" under the D35 rule."""
    if not checks.syntax_ok or checks.tests_ok is False:
        return "FAIL"
    if _gated_by_redetection(rating):
        return "PASS" if checks.redetect_ok else "FAIL"
    return "PASS" if checks.pattern_ok is True else "FAIL"


# check state of check based on its value not_run for None values,ok for True and failed for false
def _state(value: Optional[bool]) -> str:
    return "not_run" if value is None else ("ok" if value else "failed")


def build_notes(rating: Rating, checks: Checks, extra: str = "") -> str:
    """One `[evidence]` line, then optional free text.

    Example (weak/none class):
    [evidence] syntax=ok; redetect=false(not decisive); pattern_check=ok;
     tests=not_run. Not verified by re-detection.
    """

    # build the parts of the message starting with the syntax_ok
    parts = [f"syntax={_state(checks.syntax_ok)}"]

    redetect = "true" if checks.redetect_ok else "false"
    # weak/None cwe class so verdict is not gated by redetection
    if not _gated_by_redetection(rating):
        redetect += "(not decisive)"
    parts.append(f"redetect={redetect}")

    if checks.pattern_ok is not None or not _gated_by_redetection(rating):
        parts.append(f"pattern_check={_state(checks.pattern_ok)}")

    parts.append(f"tests={_state(checks.tests_ok)}")

    # Assemble the line parts
    line = EVIDENCE_PREFIX + "; ".join(parts) + "."

    # if weak/none add a tail note
    tail = [] if _gated_by_redetection(rating) else [NOT_VERIFIED_TAIL]
    if extra:
        tail.append(extra)
    return " ".join([line, *tail])


def make_report(rating: Rating, checks: Checks, extra: str = "") -> VerificationReport:
    """Build the frozen-contract VerificationReport for a fix of the given rating."""
    return VerificationReport(
        syntax_ok=checks.syntax_ok,
        tests_ok=checks.tests_ok,
        redetect_ok=checks.redetect_ok,
        verdict=decide_verdict(rating, checks),  # type: ignore[arg-type]
        notes=build_notes(rating, checks, extra),
    )
