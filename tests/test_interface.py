import json

import pytest

from shield_core.interface import (
    Finding,
    Result,
    TaintPath,
    TaintStep,
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
