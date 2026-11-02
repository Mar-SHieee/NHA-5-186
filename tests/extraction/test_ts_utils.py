import importlib

import pandas as pd
import pytest
from tree_sitter import Language

from shield_core.extraction.ts_utils import (
    FEATURE_NAMES,
    FunctionMetrics,
    _types_for,
    build_feature_table,
    compute_metrics,
    extract_functions,
)
from shield_core.languages import registry

_CATEGORIES = (
    "branches",
    "loops",
    "decisions",
    "nesting",
    "skip_nesting_under",
    "functions",
    "name_fields",
)
# These categories list grammar FIELD names (like `declarator`), not node types.
_FIELD_CATEGORIES = ("name_fields",)

# ---------------------------------------------------------------- lines and parse errors


def test_n_lines_counts_physical_lines():
    code = "def f(x):\n    return x\n"
    assert compute_metrics(code, "python").n_lines == 2


def test_n_lines_of_empty_code_is_zero():
    assert compute_metrics("", "python").n_lines == 0


def test_n_lines_in_c():
    assert compute_metrics("int main(){return 0;}", "cpp", ".c").n_lines == 1


def test_clean_code_has_no_parse_error():
    assert compute_metrics("def f(x):\n    return x\n", "python").has_parse_error is False


def test_broken_code_is_flagged():
    assert compute_metrics("def f(x:\n    return", "python").has_parse_error is True


def test_indented_method_is_not_a_parse_error():
    code = "    def f(self):\n        return 1\n"
    assert compute_metrics(code, "python").has_parse_error is False


# ---------------------------------------------------------------- branches and loops


def test_if_and_elif_are_branches():
    code = (
        "def f(x):\n"
        "    if x > 0:\n"
        "        return 1\n"
        "    elif x < 0:\n"
        "        return -1\n"
        "    return 0\n"
    )
    assert compute_metrics(code, "python").n_branches == 2


def test_for_and_while_are_loops():
    code = "def f(xs):\n    for x in xs:\n        while x:\n            x -= 1\n"
    assert compute_metrics(code, "python").n_loops == 2


def test_code_without_branches_or_loops_has_zeros():
    metrics = compute_metrics("def f(x):\n    return x\n", "python")
    assert metrics.n_branches == 0
    assert metrics.n_loops == 0


def test_c_for_while_and_if():
    code = "int f(int n){ for(int i=0;i<n;i++){ if(i%2==0){ n++; } } while(n>0){ n--; } return n; }"
    metrics = compute_metrics(code, "cpp", ".c")
    assert metrics.n_loops == 2
    assert metrics.n_branches == 1


def test_c_else_if_counts_as_two_branches():
    code = "int f(int x){ if (x>0) { return 1; } else if (x<0) { return -1; } return 0; }"
    assert compute_metrics(code, "cpp", ".c").n_branches == 2


def test_cpp_do_while_is_a_loop():
    code = "int f(){ int i=0; do { i++; } while (i<3); return i; }"
    assert compute_metrics(code, "cpp", ".cpp").n_loops == 1


# ---------------------------------------------------------------- cyclomatic complexity


def test_straight_line_code_has_cyclomatic_one():
    assert compute_metrics("def f(x):\n    return x\n", "python").cyclomatic == 1


def test_python_if_and_for_add_one_each():
    code = "def f(x):\n    if x:\n        for i in x:\n            pass\n"
    assert compute_metrics(code, "python").cyclomatic == 3


def test_python_and_or_each_add_one():
    assert compute_metrics("def f(a, b, c):\n    return a and b or c\n", "python").cyclomatic == 3


def test_python_ternary_adds_one():
    assert compute_metrics("def f(a):\n    return 1 if a else 2\n", "python").cyclomatic == 2


def test_python_each_except_adds_one():
    code = (
        "def f():\n"
        "    try:\n"
        "        pass\n"
        "    except ValueError:\n"
        "        pass\n"
        "    except KeyError:\n"
        "        pass\n"
    )
    assert compute_metrics(code, "python").cyclomatic == 3


def test_python_each_case_adds_one():
    code = (
        "def f(x):\n"
        "    match x:\n"
        "        case 1:\n"
        "            pass\n"
        "        case 2:\n"
        "            pass\n"
    )
    assert compute_metrics(code, "python").cyclomatic == 3


def test_c_logical_operators_add_one_each():
    code = "int f(int a, int b, int c){ if (a && b || c) return 1; return 0; }"
    assert compute_metrics(code, "cpp", ".c").cyclomatic == 4  # 1 + if + && + ||


def test_c_switch_counts_cases_but_not_default():
    code = "int f(int x){ switch(x){ case 1: return 1; case 2: return 2; default: return 0; } }"
    assert compute_metrics(code, "cpp", ".c").cyclomatic == 3  # 1 + two cases


def test_c_ternary_adds_one():
    assert compute_metrics("int f(int a){ return a ? 1 : 2; }", "cpp", ".c").cyclomatic == 2


def test_cpp_each_catch_adds_one():
    code = "int f(){ try { return 1; } catch (int e) { return 2; } catch (...) { return 3; } }"
    assert compute_metrics(code, "cpp", ".cpp").cyclomatic == 3


def test_cpp_and_keyword_adds_one():
    code = "bool f(bool a, bool b){ return a and b; }"
    assert compute_metrics(code, "cpp", ".cpp").cyclomatic == 2


def test_identifiers_named_and_or_are_not_decisions():
    code = "int f(int and_x, int or_y){ return and_x + or_y; }"
    assert compute_metrics(code, "cpp", ".cpp").cyclomatic == 1


# ---------------------------------------------------------------- nesting depth


def test_flat_code_has_nesting_zero():
    assert compute_metrics("def f(x):\n    return x\n", "python").max_nesting == 0


def test_python_if_inside_for_is_two_levels():
    code = "def f(x):\n    if x:\n        for i in x:\n            pass\n"
    assert compute_metrics(code, "python").max_nesting == 2


def test_python_three_levels():
    code = (
        "def f(x):\n    if x:\n        for i in x:\n            while i:\n                i -= 1\n"
    )
    assert compute_metrics(code, "python").max_nesting == 3


def test_python_elif_chain_does_not_add_levels():
    code = (
        "def f(x):\n"
        "    if x > 0:\n"
        "        pass\n"
        "    elif x < 0:\n"
        "        pass\n"
        "    else:\n"
        "        pass\n"
    )
    assert compute_metrics(code, "python").max_nesting == 1


def test_c_else_if_chain_does_not_add_levels():
    code = "int f(int x){ if (x>0) { return 1; } else if (x<0) { return -1; } else { return 0; } }"
    assert compute_metrics(code, "cpp", ".c").max_nesting == 1


def test_c_if_inside_else_block_is_a_real_level():
    code = "int f(int x){ if (x>0) { return 1; } else { if (x<0) { return -1; } } return 0; }"
    assert compute_metrics(code, "cpp", ".c").max_nesting == 2


def test_cpp_try_and_range_for_count_as_levels():
    code = "int f(int *v){ try { for (auto x : v) { } } catch (...) { } return 0; }"
    assert compute_metrics(code, "cpp", ".cpp").max_nesting == 2


# ---------------------------------------------------------------- extract_functions

_PY_FILE = (
    "import os\n"  # 1
    "\n"  # 2
    "class A:\n"  # 3
    "    @staticmethod\n"  # 4
    "    def f(x):\n"  # 5
    "        def inner():\n"  # 6
    "            pass\n"  # 7
    "        return 1\n"  # 8
    "\n"  # 9
    "def g():\n"  # 10
    "    return 2\n"  # 11
)


def test_python_functions_come_in_order_with_names_and_lines():
    funcs = extract_functions(_PY_FILE, "python")
    assert [(f.name, f.start_line, f.end_line) for f in funcs] == [("f", 5, 8), ("g", 10, 11)]


def test_python_nested_function_is_not_listed_separately():
    names = [f.name for f in extract_functions(_PY_FILE, "python")]
    assert "inner" not in names


def test_function_source_is_the_exact_text():
    funcs = extract_functions(_PY_FILE, "python")
    assert funcs[1].source == "def g():\n    return 2"
    assert funcs[1].language == "python"
    assert funcs[1].has_parse_error is False


def test_source_text_survives_non_ascii_characters():
    comment = "\u062a\u0639\u0644\u064a\u0642"  # an Arabic word, as a multi-byte comment
    code = f"def f():\n    # {comment}\n    return 1\n\ndef g():\n    return 2\n"
    funcs = extract_functions(code, "python")
    assert [f.name for f in funcs] == ["f", "g"]
    assert funcs[0].source == f"def f():\n    # {comment}\n    return 1"
    assert (funcs[1].start_line, funcs[1].end_line) == (5, 6)


def test_extracted_function_can_be_measured_again():
    for func in extract_functions(_PY_FILE, "python"):
        metrics = compute_metrics(func.source, "python")
        assert metrics.n_lines == func.end_line - func.start_line + 1
        assert metrics.has_parse_error is False


def test_file_without_functions_gives_an_empty_list():
    assert extract_functions("", "python") == []
    assert extract_functions("x = 1\n", "python") == []


def test_healthy_function_after_a_broken_one_is_still_found():
    code = "def f(x:\n    return 1\n\ndef g():\n    return 2\n"
    assert "g" in [f.name for f in extract_functions(code, "python")]


def test_c_functions_with_static_and_pointer_return():
    code = "static char *f(int a){ return 0; }\nint main(void){ return 0; }\n"
    funcs = extract_functions(code, "cpp", ".c")
    assert [(f.name, f.start_line, f.end_line) for f in funcs] == [("f", 1, 1), ("main", 2, 2)]


def test_cpp_methods_constructors_templates_and_qualified_names_are_found():
    code = (
        "namespace n {\n"
        "class B { public: int get() const { return 1; } B() {} ~B() {} };\n"
        "int B2::h(int a) { return a; }\n"
        "}\n"
        "template <typename T> T id(T x) { return x; }\n"
    )
    names = [f.name for f in extract_functions(code, "cpp", ".cpp")]
    assert names == ["get", "B", "~B", "h", "id"]


def test_healthy_c_function_after_a_broken_one_is_still_found():
    code = "int f(int a { return a; }\nint g(){ return 1; }"
    assert "g" in [f.name for f in extract_functions(code, "cpp", ".c")]


def test_disabled_language_is_refused():
    with pytest.raises(registry.DisabledLanguageError):
        extract_functions("class A {}", "java")


# ---------------------------------------------------------------- feature table

_CODE_PY = "def f(x):\n    if x:\n        for i in x:\n            pass\n"
_CODE_C = "int f(int a){ if (a && a > 1) { return 1; } return 0; }"


def _small_dataset():
    return pd.DataFrame(
        {
            "code": [_CODE_PY, _CODE_C, "def g():\n    return 1\n"],
            "language": ["python", "cpp", "python"],
            "label": [1, 0, 1],
        },
        index=[10, 20, 30],
    )


def test_feature_table_columns_are_the_metric_fields_in_order():
    assert list(build_feature_table(_small_dataset()).columns) == list(FEATURE_NAMES)
    assert FEATURE_NAMES == (
        "n_lines",
        "n_branches",
        "n_loops",
        "cyclomatic",
        "max_nesting",
        "has_parse_error",
    )


def test_feature_table_rows_equal_compute_metrics_row_by_row():
    df = _small_dataset()
    table = build_feature_table(df)
    for label, code, language in zip(df.index, df["code"], df["language"], strict=True):
        expected = compute_metrics(code, language)
        for name in FEATURE_NAMES:
            assert table.loc[label, name] == getattr(expected, name)


def test_feature_table_keeps_the_index_so_a_join_lines_up():
    df = _small_dataset()
    joined = df.join(build_feature_table(df))
    assert list(joined.index) == [10, 20, 30]
    assert joined.loc[20, "cyclomatic"] == 3  # 1 + if + &&
    assert joined.loc[20, "label"] == 0


def test_feature_table_has_compact_dtypes():
    table = build_feature_table(_small_dataset())
    assert table["n_lines"].dtype == "int32"
    assert table["cyclomatic"].dtype == "int32"
    assert table["has_parse_error"].dtype == "bool"


def test_feature_table_of_an_empty_dataset_is_empty_with_the_same_columns():
    empty = pd.DataFrame({"code": [], "language": []})
    table = build_feature_table(empty)
    assert len(table) == 0
    assert list(table.columns) == list(FEATURE_NAMES)
    assert table["has_parse_error"].dtype == "bool"


def test_feature_table_does_not_change_its_input():
    df = _small_dataset()
    before = df.copy()
    build_feature_table(df)
    pd.testing.assert_frame_equal(df, before)


def test_feature_table_accepts_other_column_names():
    df = _small_dataset().rename(columns={"code": "func", "language": "lang"})
    table = build_feature_table(df, code_col="func", language_col="lang")
    assert table.loc[10, "max_nesting"] == 2


def test_feature_table_names_the_row_when_code_is_missing():
    df = pd.DataFrame({"code": pd.Series(["x = 1", pd.NA], dtype="string"), "language": "python"})
    with pytest.raises(ValueError, match="row 1"):
        build_feature_table(df)


def test_feature_table_names_the_row_when_language_is_missing():
    df = pd.DataFrame({"code": ["x = 1"], "language": pd.Series([pd.NA], dtype="string")})
    with pytest.raises(ValueError, match="row 0"):
        build_feature_table(df)


def test_feature_table_refuses_a_disabled_language():
    df = pd.DataFrame({"code": ["class A {}"], "language": ["java"]})
    with pytest.raises(registry.DisabledLanguageError):
        build_feature_table(df)


def test_feature_names_match_the_metrics_dataclass():
    metrics = compute_metrics("x = 1", "python")
    assert isinstance(metrics, FunctionMetrics)
    assert set(FEATURE_NAMES) == set(metrics.__dataclass_fields__)


# ---------------------------------------------------------------- guards on the YAML


def test_missing_category_is_an_error_not_zero():
    with pytest.raises(ValueError, match="no 'ts_nodes.nonexistent' list"):
        _types_for(registry.get("python"), "nonexistent")


_ENABLED = [s for s in registry.all_languages() if s.enabled]


@pytest.mark.parametrize("spec", _ENABLED, ids=lambda s: s.name)
def test_every_enabled_language_lists_every_category(spec):
    for category in _CATEGORIES:
        assert category in spec.ts_nodes, f"{spec.name}.yaml has no 'ts_nodes.{category}'"


def _grammars_of(spec):
    names = {spec.tree_sitter.default, *spec.tree_sitter.by_extension.values()}
    return [Language(importlib.import_module(n).language()) for n in sorted(names)]


def _kind_exists(grammar, kind):
    # named nodes (if_statement) and anonymous tokens ("&&", "case") are looked up separately
    return bool(grammar.id_for_node_kind(kind, True) or grammar.id_for_node_kind(kind, False))


def _field_exists(grammar, field):
    return grammar.field_id_for_name(field) is not None


@pytest.mark.parametrize("spec", _ENABLED, ids=lambda s: s.name)
def test_every_ts_node_type_in_the_yaml_exists_in_a_grammar(spec):
    grammars = _grammars_of(spec)
    for category, names in spec.ts_nodes.items():
        exists = _field_exists if category in _FIELD_CATEGORIES else _kind_exists
        for name in names:
            found = any(exists(g, name) for g in grammars)
            assert found, f"{spec.name}.yaml: '{name}' ({category}) is not in the grammar"
