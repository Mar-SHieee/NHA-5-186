import json

import pytest

from shield_core.interface import (
    Finding,
    ModelUnavailableError,
    RepoNotFoundError,
    Result,
    ShieldError,
    TaintPath,
    TaintStep,
    UnsupportedLanguageError,
    predict,
    scan_repo,
    suggest_fix,
)


def test_predict_stub_roundtrips_json():
    r = predict("print('hi')", "python")
    d = json.loads(json.dumps(r.to_dict()))
    assert d["schema_version"] == "1.0"
    assert d["vulnerable"] is False and d["cwe"] is None


def test_unsupported_language_raises():
    with pytest.raises(ValueError):
        predict("x", "cobol")


def test_nested_chain_serializes():
    step = TaintStep(file="app.py", line=5, code="user_id = request.args['id']")
    path = TaintPath(source="request.args", sink="cursor.execute", steps=[step])
    f = Finding(cwe="CWE-89", confidence=0.91, language="python", taint_paths=[path])
    r = Result(vulnerable=True, cwe="CWE-89", confidence=0.91, findings=[f])
    d = json.loads(json.dumps(r.to_dict()))
    assert d["findings"][0]["taint_paths"][0]["steps"][0]["line"] == 5


def test_suggest_fix_stub():
    f = Finding(cwe="CWE-89", confidence=0.9, language="python")
    fx = suggest_fix(f)
    assert fx.status == "no_fix_available" and fx.candidate_fix is None
    assert fx.to_dict()["schema_version"] == "1.0"


def test_scan_repo_stub():
    assert scan_repo(".").to_dict()["files"] == {}


def test_suggest_fix_accepts_code():
    f = Finding(cwe="CWE-89", confidence=0.9, language="python")
    fx = suggest_fix(f, code="cursor.execute(q)")
    assert fx.status == "no_fix_available"
    assert fx.finding is f


def test_suggest_fix_code_is_optional():
    f = Finding(cwe="CWE-89", confidence=0.9, language="python", file="app.py")
    assert suggest_fix(f).status == "no_fix_available"


def test_scan_repo_missing_path_raises(tmp_path):
    with pytest.raises(RepoNotFoundError):
        scan_repo(str(tmp_path / "nope"))


def test_scan_repo_file_is_not_a_repo(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    with pytest.raises(RepoNotFoundError):
        scan_repo(str(f))


def test_disabled_language_raises_unsupported():
    with pytest.raises(UnsupportedLanguageError):  # java exists but is disabled
        predict("class X {}", "java")


def test_error_hierarchy():
    assert issubclass(UnsupportedLanguageError, ValueError)
    assert issubclass(RepoNotFoundError, FileNotFoundError)
    assert issubclass(ModelUnavailableError, RuntimeError)
    for cls in (UnsupportedLanguageError, RepoNotFoundError, ModelUnavailableError):
        assert issubclass(cls, ShieldError)


def test_versions_exist():
    from shield_core.interface import INTERFACE_VERSION, SCHEMA_VERSION

    assert INTERFACE_VERSION == "1.0" and SCHEMA_VERSION == "1.0"
