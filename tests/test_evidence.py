"""D35: verdict rule and notes prefix (shield_core/verify/evidence.py)."""

import pytest

from shield_core.interface import VerificationReport
from shield_core.verify.evidence import (
    EVIDENCE_PREFIX,
    Checks,
    Rating,
    build_notes,
    decide_verdict,
    make_report,
)

ALL_OK = Checks(syntax_ok=True, redetect_ok=True, tests_ok=True, pattern_ok=True)


# --- Strong: PASS needs syntax_ok, redetect_ok, tests_ok not False --------------------------


def test_strong_passes_when_all_checks_pass():
    assert decide_verdict(Rating.STRONG, ALL_OK) == "PASS"


def test_strong_passes_when_tests_were_not_run():
    checks = Checks(syntax_ok=True, redetect_ok=True, tests_ok=None)
    assert decide_verdict(Rating.STRONG, checks) == "PASS"


@pytest.mark.parametrize(
    "checks",
    [
        Checks(syntax_ok=False, redetect_ok=True, tests_ok=True),
        Checks(syntax_ok=True, redetect_ok=False, tests_ok=True),
        Checks(syntax_ok=True, redetect_ok=True, tests_ok=False),
    ],
)
def test_strong_fails_when_a_gate_fails(checks):
    assert decide_verdict(Rating.STRONG, checks) == "FAIL"


# --- Weak / None: re-detection is not a gate; the syntactic check is -------------------------


@pytest.mark.parametrize("rating", [Rating.WEAK, Rating.NONE])
def test_weak_none_pass_although_redetection_still_reports_a_flow(rating):
    # The CWE-22 / CWE-78 case: a correct fix is still reported by the detector (py19, py20).
    checks = Checks(syntax_ok=True, redetect_ok=False, tests_ok=None, pattern_ok=True)
    assert decide_verdict(rating, checks) == "PASS"


@pytest.mark.parametrize("rating", [Rating.WEAK, Rating.NONE])
@pytest.mark.parametrize(
    "checks",
    [
        Checks(syntax_ok=False, redetect_ok=False, tests_ok=None, pattern_ok=True),
        Checks(syntax_ok=True, redetect_ok=True, tests_ok=None, pattern_ok=False),
        Checks(syntax_ok=True, redetect_ok=True, tests_ok=None, pattern_ok=None),  # not run
        Checks(syntax_ok=True, redetect_ok=False, tests_ok=False, pattern_ok=True),
    ],
)
def test_weak_none_fail_when_syntax_pattern_or_tests_fail(rating, checks):
    assert decide_verdict(rating, checks) == "FAIL"


def test_a_quiet_detector_alone_never_passes_a_weak_class():
    # The false-pass direction (C CWE-120: strncpy loses taint): redetect_ok is True,
    # but without the syntactic check the fix must not pass.
    checks = Checks(syntax_ok=True, redetect_ok=True, tests_ok=None, pattern_ok=None)
    assert decide_verdict(Rating.NONE, checks) == "FAIL"


# --- Notes: first line is the [evidence] line ------------------------------------------------


def test_notes_match_the_agreed_example_for_a_weak_class():
    checks = Checks(syntax_ok=True, redetect_ok=False, tests_ok=None, pattern_ok=True)
    assert build_notes(Rating.NONE, checks) == (
        "[evidence] syntax=ok; redetect=false(not decisive); pattern_check=ok; tests=not_run. "
        "Not verified by re-detection."
    )


def test_notes_for_a_strong_class_omit_the_pattern_check_when_not_configured():
    checks = Checks(syntax_ok=True, redetect_ok=True, tests_ok=None)
    assert build_notes(Rating.STRONG, checks, "No test suite found.") == (
        "[evidence] syntax=ok; redetect=true; tests=not_run. No test suite found."
    )


@pytest.mark.parametrize("rating", list(Rating))
def test_notes_always_start_with_the_evidence_prefix(rating):
    assert build_notes(rating, ALL_OK).startswith(EVIDENCE_PREFIX)


def test_only_weak_none_notes_say_not_verified_by_redetection():
    assert "Not verified by re-detection." not in build_notes(Rating.STRONG, ALL_OK)
    assert "Not verified by re-detection." in build_notes(Rating.WEAK, ALL_OK)
    assert "Not verified by re-detection." in build_notes(Rating.NONE, ALL_OK)


def test_failed_checks_are_named_as_failed():
    checks = Checks(syntax_ok=False, redetect_ok=True, tests_ok=False, pattern_ok=False)
    notes = build_notes(Rating.WEAK, checks)
    assert "syntax=failed" in notes and "pattern_check=failed" in notes and "tests=failed" in notes


# --- The report keeps the frozen contract shape ----------------------------------------------


def test_make_report_returns_a_contract_verification_report():
    checks = Checks(syntax_ok=True, redetect_ok=False, tests_ok=None, pattern_ok=True)
    report = make_report(Rating.NONE, checks)
    assert isinstance(report, VerificationReport)
    assert report.verdict == "PASS"
    assert report.redetect_ok is False  # the real detector result is kept
    assert set(report.to_dict()) == {"syntax_ok", "tests_ok", "redetect_ok", "verdict", "notes"}
    assert report.notes.startswith(EVIDENCE_PREFIX)
