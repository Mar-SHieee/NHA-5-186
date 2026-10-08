import json
from dataclasses import fields

import pytest

from languages import registry
from shield_core import cli
from shield_core.cli import main
from shield_core.interface import SCHEMA_VERSION, Result


@pytest.fixture
def seen_language(monkeypatch):
    seen = []
    real_predict = cli.predict

    def spy(code, language):
        seen.append(language)
        return real_predict(code, language)

    monkeypatch.setattr(cli, "predict", spy)
    return seen


def test_scan_python_file_returns_stub_result(tmp_path, capsys, seen_language):
    f = tmp_path / "x.py"
    f.write_text("print('hi')\n")

    assert main(["scan", str(f)]) == 0

    data = json.loads(capsys.readouterr().out)
    assert set(data) == {fld.name for fld in fields(Result)}
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["vulnerable"] is False
    assert seen_language == ["python"]


def test_scan_c_file_uses_the_cpp_language(tmp_path, seen_language):
    f = tmp_path / "x.c"
    f.write_text("int main(void) { return 0; }\n")

    assert main(["scan", str(f)]) == 0
    assert seen_language == ["cpp"]


def test_language_flag_overrides_the_extension(tmp_path, seen_language):
    f = tmp_path / "snippet.txt"
    f.write_text("x = 1\n")

    assert main(["scan", str(f), "--language", "python"]) == 0
    assert seen_language == ["python"]


def test_disabled_language_lists_enabled_languages(tmp_path, capsys):
    f = tmp_path / "X.java"
    f.write_text("class X {}\n")

    assert main(["scan", str(f)]) == 2

    err = capsys.readouterr().err
    assert "unsupported language" in err
    for name in registry.enabled_languages():
        assert name in err


def test_unknown_extension_lists_enabled_languages(tmp_path, capsys):
    f = tmp_path / "notes.txt"
    f.write_text("hello\n")

    assert main(["scan", str(f)]) == 2

    err = capsys.readouterr().err
    assert "unsupported file type" in err
    for name in registry.enabled_languages():
        assert name in err


def test_missing_file_is_a_clean_error(tmp_path, capsys):
    assert main(["scan", str(tmp_path / "nope.py")]) == 2
    assert "file not found" in capsys.readouterr().err
