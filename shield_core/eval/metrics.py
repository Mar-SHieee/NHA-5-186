from sklearn.metrics import confusion_matrix, precision_recall_fscore_support


def calculate_metrics(y_true, y_pred):
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="weighted", zero_division=0
    )
    return {"precision": float(precision), "recall": float(recall), "f1": float(f1)}


def calculate_confusion_matrix(y_true, y_pred):
    cm = confusion_matrix(y_true, y_pred)
    return cm.tolist()
