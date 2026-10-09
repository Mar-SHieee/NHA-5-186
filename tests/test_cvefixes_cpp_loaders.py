"""Unit tests for the C/C++ CVEfixes loader, on tiny synthetic tables."""

import pandas as pd
import pytest

from shield_core.datasets.c_cpp_loaders.cvefixes_cpp_loaders import CVEfixesCppLoader


@pytest.fixture
def loader():
    return CVEfixesCppLoader()


@pytest.fixture
def method_change():
    """Four old functions, each one a different pairing scenario."""
    rows = [
        # 1) normal fix: same signature before and after -> matched
        (1, "parse(char *buf)", "old_parse", "True"),
        (1, "parse(char *buf)", "new_parse", "False"),
        # 2) function deleted in the fix -> no patched version
        (2, "helper()", "old_helper", "True"),
        # 3) signature changed (parameter added) -> no match
        (3, "copy(char *buf)", "old_copy", "True"),
        (3, "copy(char *buf, size_t len)", "new_copy", "False"),
        # 4) patched code identical to old code -> not a real fix
        (4, "noop()", "same_code", "True"),
        (4, "noop()", "same_code", "False"),
    ]
    return pd.DataFrame(rows, columns=["file_change_id", "signature", "code", "before_change"])


def _fixed_by_old_code(pairs: pd.DataFrame) -> dict:
    return pairs.set_index("code")["fixed_code"].to_dict()


def test_pairs_old_with_new_on_signature(loader, method_change):
    fixed = _fixed_by_old_code(loader._pair_old_with_new(method_change))
    assert fixed["old_parse"] == "new_parse"


def test_deleted_function_has_no_fix(loader, method_change):
    fixed = _fixed_by_old_code(loader._pair_old_with_new(method_change))
    assert pd.isna(fixed["old_helper"])


def test_changed_signature_has_no_match(loader, method_change):
    fixed = _fixed_by_old_code(loader._pair_old_with_new(method_change))
    assert pd.isna(fixed["old_copy"])


def test_identical_fix_is_blanked(loader, method_change):
    pairs = loader._pair_old_with_new(method_change)
    fixed = _fixed_by_old_code(loader._blank_identical_fixes(pairs))
    assert pd.isna(fixed["same_code"])


def test_safe_samples_only_from_real_fixes(loader, method_change):
    pairs = loader._blank_identical_fixes(loader._pair_old_with_new(method_change))
    safe = loader._create_safe_samples(pairs.assign(cwe="CWE-787"))
    assert list(safe["code"]) == ["new_parse"]
    assert (safe["label"] == 0).all()
    assert safe["cwe"].isna().all()


def test_language_map_keeps_c_and_cpp_apart(loader):
    df = pd.DataFrame({"language": ["C", "C++", "Python"]})
    kept = loader._normalize_language(loader._filter_c_cpp_only(df))
    assert list(kept["language"]) == ["c", "cpp"]
