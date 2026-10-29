from shield_core.eval.metrics import (
    calculate_metrics,
    commits_per_cwe,
    cwe_confusion_matrix,
    per_cwe_metrics,
    per_cwe_metrics_by_language,
)


def test_metrics_basic():
    y_true = [0, 1, 1, 0, 1]
    y_pred = [0, 1, 0, 0, 1]

    res = calculate_metrics(y_true, y_pred)
    assert "precision" in res
    assert "recall" in res
    assert "f1" in res


def test_metrics_zero_predictions():
    y_true = [1, 1, 1]
    y_pred = [0, 0, 0]

    res = calculate_metrics(y_true, y_pred)
    assert res["precision"] == 0.0
    assert res["recall"] == 0.0
    assert res["f1"] == 0.0


def test_cwe_with_zero_predictions():
    y_true = ["CWE-79"] * 9 + ["CWE-22"]
    y_pred = ["CWE-79"] * 10

    rows = {row["cwe"]: row for row in per_cwe_metrics(y_true, y_pred)}
    assert rows["CWE-22"]["recall"] == 0.0
    assert rows["CWE-22"]["f1"] == 0.0
    assert rows["CWE-22"]["support"] == 1


def test_cwe_absent_from_split():
    y_true = ["CWE-79", "CWE-79"]
    y_pred = ["CWE-79", "CWE-89"]

    rows = {row["cwe"]: row for row in per_cwe_metrics(y_true, y_pred)}
    assert rows["CWE-89"]["precision"] == 0.0
    assert rows["CWE-89"]["support"] == 0


def test_multilabel_row():
    y_true = [["CWE-79", "CWE-20"], ["CWE-79", "CWE-20"]]
    y_pred = ["CWE-20", "CWE-89"]

    rows = {row["cwe"]: row for row in per_cwe_metrics(y_true, y_pred)}
    assert rows["CWE-20"]["recall"] == 1.0
    assert rows["CWE-79"]["recall"] == 0.0


def test_per_language():
    y_true = ["CWE-79", "CWE-79", "CWE-787", "CWE-787"]
    y_pred = ["CWE-79", "CWE-79", "CWE-787", "CWE-125"]
    languages = ["python", "python", "cpp", "cpp"]

    result = per_cwe_metrics_by_language(y_true, y_pred, languages)
    python_rows = {row["cwe"]: row for row in result["python"]}
    cpp_rows = {row["cwe"]: row for row in result["cpp"]}

    assert python_rows["CWE-79"]["recall"] == 1.0
    assert cpp_rows["CWE-787"]["recall"] == 0.5


def test_cwe_confusion_matrix():
    y_true = ["CWE-79"] * 9 + ["CWE-22"]
    y_pred = ["CWE-79"] * 10

    result = cwe_confusion_matrix(y_true, y_pred)
    assert result["labels"] == ["CWE-22", "CWE-79"]
    assert result["counts"] == [[0, 1], [0, 9]]


def test_commits_per_cwe():
    cwes = ["CWE-79", "CWE-79", "CWE-79", "CWE-444", "CWE-444", "CWE-444"]
    commits = ["a1", "b2", "c3", "x9", "x9", "y9"]

    result = commits_per_cwe(cwes, commits)
    assert result["CWE-79"] == {"commits": 3, "reliable": True}
    assert result["CWE-444"] == {"commits": 2, "reliable": False}
