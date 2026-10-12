import re
from pathlib import Path

import pytest
import yaml

from languages import registry
from languages.registry import (
    DisabledLanguageError,
    LanguageConfigError,
    SinkSpec,
    SourceSpec,
    UnknownLanguageError,
    load_registry,
)

GUARDED = ["shield_core/interface.py", "shield_core/cli.py"]


def test_all_three_files_load():
    assert [spec.name for spec in registry.all_languages()] == ["cpp", "java", "python"]


def test_enabled_languages_are_python_and_cpp():
    assert registry.enabled_languages() == ["cpp", "python"]


def test_java_is_known_but_disabled():
    assert registry.get("java").enabled is False
    assert registry.is_enabled("java") is False
    with pytest.raises(DisabledLanguageError, match="cpp, python"):
        registry.require_enabled("java")


def test_unknown_language_raises():
    with pytest.raises(UnknownLanguageError, match="cobol"):
        registry.get("cobol")
    assert registry.is_enabled("cobol") is False


def test_require_enabled_returns_the_spec():
    assert registry.require_enabled("python").joern_frontend == "PYTHONSRC"


@pytest.mark.parametrize(
    ("extension", "expected"),
    [
        (".py", "python"),
        (".PY", "python"),
        (".c", "cpp"),
        (".hpp", "cpp"),
        (".java", "java"),
    ],
)
def test_language_for_extension(extension, expected):
    assert registry.language_for_extension(extension).name == expected  # type: ignore


def test_unknown_extension_returns_none():
    assert registry.language_for_extension(".txt") is None
    assert registry.language_for_path("README") is None


def test_language_for_path_uses_the_suffix():
    assert registry.language_for_path("some/dir/app.py").name == "python"  # type: ignore


def test_tree_sitter_grammar_by_extension():
    ts = registry.get("cpp").tree_sitter
    assert ts.module_for(".c") == "tree_sitter_c"
    assert ts.module_for(".cpp") == "tree_sitter_cpp"
    assert ts.module_for() == "tree_sitter_cpp"
    assert registry.get("python").tree_sitter.module_for(".py") == "tree_sitter_python"


# ----------------------------- the validation rules -------------------------------------

BASE = {
    "name": "demo",
    "enabled": True,
    "extensions": [".dm"],
    "joern_frontend": "DEMO",
    "tree_sitter": {"default": "tree_sitter_demo"},
    "cwes": [],
    "sources": [],
    "sinks": [],
    "sanitizers": [],
}
REMOVE = object()


def write(folder, changes=None, filename="demo.yaml"):
    data = dict(BASE)
    for key, value in (changes or {}).items():
        if value is REMOVE:
            data.pop(key)
        else:
            data[key] = value
    (folder / filename).write_text(yaml.safe_dump(data), encoding="utf-8")


def test_a_valid_file_loads(tmp_path):
    write(tmp_path)
    specs = load_registry(tmp_path)
    assert specs["demo"].extensions == (".dm",)
    assert specs["demo"].cwes == ()


def test_sources_sinks_and_sanitizers_are_parsed(tmp_path):
    write(
        tmp_path,
        {
            "sources": [{"kind": "call", "code": r"request\.args\[.*"}],
            "sinks": [
                {"name": "execute", "arg": 1, "cwe": "CWE-89"},
                {"name": "run", "code": r"subprocess\.run.*", "arg": 1},
            ],
            "sanitizers": ["int"],
        },
    )
    spec = load_registry(tmp_path)["demo"]
    assert spec.sources == (SourceSpec(kind="call", code=r"request\.args\[.*"),)
    assert spec.sinks[0] == SinkSpec(name="execute", arg=1, cwe="CWE-89")
    assert spec.sinks[1].code == r"subprocess\.run.*"
    assert spec.sanitizers == ("int",)


def test_every_source_kind_and_arg_from_are_parsed(tmp_path):
    write(
        tmp_path,
        {
            "sources": [
                {"kind": "call", "name": "getenv"},
                {"kind": "argument", "name": "read|recv", "arg": 2},
                {"kind": "parameter", "name": "argv"},
            ],
            "sinks": [{"name": "sprintf", "arg_from": 3, "cwe": "CWE-120"}],
        },
    )
    spec = load_registry(tmp_path)["demo"]
    assert spec.sources == (
        SourceSpec(kind="call", name="getenv"),
        SourceSpec(kind="argument", name="read|recv", arg=2),
        SourceSpec(kind="parameter", name="argv"),
    )
    assert spec.sinks == (SinkSpec(name="sprintf", arg_from=3, cwe="CWE-120"),)
    assert spec.sinks[0].arg is None


def test_cpp_taint_config_matches_the_spike():
    cpp = registry.get("cpp")
    kinds = {(s.kind, s.name, s.arg) for s in cpp.sources}
    assert ("call", "getenv", None) in kinds
    assert ("argument", "fgets", 1) in kinds  # the CALL as a source gave 0 flows (c03)
    assert ("argument", "read|recv", 2) in kinds
    assert ("parameter", "argv", None) in kinds
    assert {(s.name, s.arg) for s in cpp.sinks} >= {("system", 1), ("strcpy", 2), ("memcpy", 3)}
    assert "realpath" in cpp.sanitizers
    assert not any(re.fullmatch(p, "strncpy") for p in cpp.sanitizers)


BAD_FILES = [
    ({"sinks": REMOVE}, "missing keys: sinks"),
    ({"sanitizers": REMOVE}, "missing keys: sanitizers"),
    ({"sanitizers": "int"}, "'sanitizers' must be a list"),
    ({"sanitizers": ["("]}, "not a valid regex"),
    ({"sources": ["eval"]}, "'sources[0]' must be a mapping"),
    ({"sources": [{"kind": "stdin", "name": "fgets"}]}, "'kind' must be one of"),
    ({"sources": [{"kind": "argument", "name": "fgets"}]}, "of kind 'argument' needs 'arg'"),
    ({"sources": [{"kind": "argument", "arg": 1}]}, "of kind 'argument' needs 'name'"),
    ({"sources": [{"kind": "argument", "name": "fgets", "arg": -1}]}, "'arg' must be an integer"),
    ({"sources": [{"kind": "argument", "name": "fgets", "arg": True}]}, "'arg' must be an integer"),
    ({"sources": [{"kind": "call", "name": "getenv", "arg": 1}]}, "only valid for kind 'argument'"),
    ({"sources": [{"kind": "parameter", "code": "argv"}]}, "of kind 'parameter' needs 'name'"),
    ({"sources": [{"kind": "parameter", "name": "argv", "arg": 1}]}, "takes only 'name'"),
    ({"sources": [{"kind": "call"}]}, "needs 'name' or 'code'"),
    ({"sources": [{"kind": "call", "code": "x", "typo": 1}]}, "unknown keys in 'sources[0]'"),
    ({"sinks": [{"arg": 1}]}, "is missing: name"),
    ({"sinks": [{"name": "execute"}]}, "needs one of 'arg' or 'arg_from'"),
    ({"sinks": [{"name": "execute", "arg": 1, "arg_from": 2}]}, "cannot have both"),
    ({"sinks": [{"name": "sprintf", "arg_from": 0}]}, "'arg_from' must be an integer >= 1"),
    ({"sinks": [{"name": "sprintf", "arg_from": "3"}]}, "'arg_from' must be an integer"),
    ({"sinks": [{"name": "execute", "arg": "1"}]}, "'arg' must be an integer"),
    ({"sinks": [{"name": "execute", "arg": True}]}, "'arg' must be an integer"),
    ({"sinks": [{"name": "execute", "arg": -1}]}, "'arg' must be an integer"),
    ({"sinks": [{"name": "execute", "arg": 1, "cwe": "89"}]}, "invalid 'cwe'"),
    ({"sinks": [{"name": "(", "arg": 1}]}, "not a valid regex"),
    ({"enabeld": True}, "unknown keys: enabeld"),
    ({"name": "other"}, "must match the file name"),
    ({"name": "Demo"}, "lowercase letters"),
    ({"enabled": "yes"}, "'enabled' must be true or false"),
    ({"extensions": ["dm"]}, "start with a dot"),
    ({"extensions": [".DM"]}, "start with a dot"),
    ({"extensions": []}, "'extensions' must be a non-empty list"),
    ({"joern_frontend": ""}, "'joern_frontend' must be a non-empty string"),
    ({"cwes": ["789"]}, "invalid entry"),
    ({"cwes": None}, "write 'cwes: []'"),
    ({"sources": "eval"}, "'sources' must be a list"),
    ({"tree_sitter": {}}, "tree_sitter.default"),
    (
        {"tree_sitter": {"default": "x", "by_extension": {".zz": "y"}}},
        "not in 'extensions'",
    ),
]


@pytest.mark.parametrize(("changes", "expected"), BAD_FILES)
def test_broken_files_are_rejected_with_a_clear_message(tmp_path, changes, expected):
    write(tmp_path, changes)
    with pytest.raises(LanguageConfigError, match=re.escape(expected)) as info:
        load_registry(tmp_path)
    assert "demo.yaml" in str(info.value)


def test_extension_cannot_belong_to_two_languages(tmp_path):
    write(tmp_path)
    write(tmp_path, {"name": "other"}, filename="other.yaml")
    with pytest.raises(LanguageConfigError, match="already used by"):
        load_registry(tmp_path)


def test_empty_folder_is_an_error(tmp_path):
    with pytest.raises(LanguageConfigError, match=re.escape("no *.yaml language files")):
        load_registry(tmp_path)


def test_invalid_yaml_is_an_error(tmp_path):
    (tmp_path / "demo.yaml").write_text("name: [unclosed\n", encoding="utf-8")
    with pytest.raises(LanguageConfigError, match="invalid YAML"):
        load_registry(tmp_path)


def test_file_that_is_not_a_mapping_is_an_error(tmp_path):
    (tmp_path / "demo.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(LanguageConfigError, match="mapping"):
        load_registry(tmp_path)


def test_no_language_literals_outside_registry():
    root = Path(__file__).resolve().parents[1]
    names = [s.name for s in registry.all_languages()]
    pattern = re.compile(r"""["'](%s)["']""" % "|".join(names))
    for rel in GUARDED:
        for n, line in enumerate((root / rel).read_text().splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            assert not pattern.search(line), f"{rel}:{n} hardcodes a language: {line.strip()}"
