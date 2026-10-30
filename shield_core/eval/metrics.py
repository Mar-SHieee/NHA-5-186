from sklearn.metrics import confusion_matrix, precision_recall_fscore_support


def calculate_metrics(y_true, y_pred):
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="weighted", zero_division=0
    )
    return {"precision": float(precision), "recall": float(recall), "f1": float(f1)}


def calculate_confusion_matrix(y_true, y_pred):
    cm = confusion_matrix(y_true, y_pred)
    return cm.tolist()


def _pick_true_cwe(actual_cwe, pred):
    """If a row has several CWEs, count the prediction as correct when it is one of them."""
    if isinstance(actual_cwe, str):
        return actual_cwe
    actual_cwe = list(actual_cwe)
    if pred in actual_cwe:
        return pred
    return actual_cwe[0]


def per_cwe_metrics(y_true, y_pred):
    y_true = [_pick_true_cwe(t, p) for t, p in zip(y_true, y_pred, strict=True)]
    labels = sorted(set(y_true) | set(y_pred))
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, average=None, zero_division=0
    )
    results = []
    for i, cwe in enumerate(labels):
        results.append(
            {
                "cwe": cwe,
                "precision": float(precision[i]),
                "recall": float(recall[i]),
                "f1": float(f1[i]),
                "support": int(support[i]),
            }
        )
    return results


def per_cwe_metrics_by_language(y_true, y_pred, languages):
    results = {}
    for language in sorted(set(languages)):
        rows = [i for i, lang in enumerate(languages) if lang == language]
        lang_true = [y_true[i] for i in rows]
        lang_pred = [y_pred[i] for i in rows]
        results[language] = per_cwe_metrics(lang_true, lang_pred)
    return results


def cwe_confusion_matrix(y_true, y_pred):
    y_true = [_pick_true_cwe(t, p) for t, p in zip(y_true, y_pred, strict=True)]
    labels = sorted(set(y_true) | set(y_pred))
    counts = confusion_matrix(y_true, y_pred, labels=labels)
    return {"labels": labels, "counts": counts.tolist()}


def commits_per_cwe(cwes, commits, min_commits=3):
    found = {}
    for cwe, commit in zip(cwes, commits, strict=True):
        found.setdefault(cwe, set()).add(commit)
    return {cwe: {"commits": len(c), "reliable": len(c) >= min_commits} for cwe, c in found.items()}
