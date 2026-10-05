from eval.metrics import calculate_metrics


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
