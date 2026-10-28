"""Evaluate the saved V1 family classifier on the held-out test embeddings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)

from scripts.training.v1_pipeline import ROOT, first_cwe, load_precomputed_split


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _metadata_codes(path: Path, language: str) -> set[str]:
    frame = pd.read_parquet(path)
    if language != "all":
        frame = frame[frame.language.eq(language)]
    if "code" not in frame:
        raise ValueError(f"{path} must include code so split leakage can be filtered")
    codes = frame.code.fillna("").astype(str)
    return set(codes[codes.str.strip().ne("")].drop_duplicates())


def _metrics(true, pred, labels):
    precision, recall, f1, support = precision_recall_fscore_support(
        true, pred, labels=labels, zero_division=0
    )
    return {
        "accuracy": float(accuracy_score(true, pred)),
        "macro_f1": float(f1_score(true, pred, labels=labels, average="macro", zero_division=0)),
        "weighted_f1": float(
            f1_score(true, pred, labels=labels, average="weighted", zero_division=0)
        ),
        "support": int(len(true)),
        "per_family": {
            family: {
                "precision": float(precision[i]),
                "recall": float(recall[i]),
                "f1": float(f1[i]),
                "support": int(support[i]),
            }
            for i, family in enumerate(labels)
        },
        "confusion_matrix": {
            "labels": labels,
            "counts": confusion_matrix(true, pred, labels=labels).tolist(),
        },
    }


def evaluate(run_dir: Path) -> dict:
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    prep = joblib.load(run_dir / "preprocessing.joblib")
    family_classes = prep.get("family_classes")
    if not family_classes:
        raise ValueError("This V1 artifact has no saved family classifier metadata")
    model_path = run_dir / "family_model.json"
    family_model = None
    if model_path.exists():
        from xgboost import XGBClassifier

        family_model = XGBClassifier()
        family_model.load_model(str(model_path))
    elif prep.get("family_constant") is None:
        raise FileNotFoundError(f"Missing family classifier: {model_path}")

    splits_dir = _path(config["splits_dir"])
    language = config.get("language", "all")
    train_codes = _metadata_codes(splits_dir / "train.parquet", language)
    val_codes = _metadata_codes(splits_dir / "val.parquet", language) - train_codes
    test_frame, test_vectors = load_precomputed_split(
        splits_dir / "test.parquet",
        _path(config["embedding_files"]["test"]),
        language,
        _path(config["assignment_file"]) if config.get("assignment_file") else None,
        "test",
    )
    keep = ~test_frame.code.isin(train_codes | val_codes).to_numpy()
    test_frame = test_frame.loc[keep].reset_index(drop=True)
    test_vectors = test_vectors[keep]
    labeled = test_frame.label.eq(1).to_numpy() & test_frame.cwe.notna().to_numpy()
    test_frame = test_frame.loc[labeled].reset_index(drop=True)
    test_vectors = test_vectors[labeled]
    if not len(test_frame):
        raise ValueError("No labeled vulnerable rows remain in the held-out test split")

    family_spec_path = _path(config.get("cwe_family_map", "scripts/training/cwe_family_map.json"))
    family_spec = json.loads(family_spec_path.read_text(encoding="utf-8"))
    mapping = family_spec["cwe_to_family"]
    fallback = family_spec.get("fallback_family", "other")
    true_families = np.asarray(
        [mapping.get(first_cwe(value), fallback) for value in test_frame.cwe], dtype=object
    )
    if family_model is None:
        pred_ids = np.repeat(int(prep["family_constant"]), len(test_frame))
    else:
        pred_ids = family_model.predict(test_vectors).astype(int)
    pred_families = np.asarray(family_classes, dtype=object)[pred_ids]
    labels = sorted(set(true_families) | set(pred_families))
    unseen = sorted(set(true_families) - set(family_classes))

    result = {
        "run_dir": str(run_dir),
        "split": "test",
        "rows": int(len(test_frame)),
        "family_classes_trained": family_classes,
        "true_families_absent_from_training": unseen,
        "overall": _metrics(true_families, pred_families, labels),
        "by_language": {},
    }
    for lang in sorted(test_frame.language.astype(str).unique()):
        mask = test_frame.language.astype(str).eq(lang).to_numpy()
        language_labels = sorted(set(true_families[mask]) | set(pred_families[mask]))
        result["by_language"][lang] = _metrics(
            true_families[mask], pred_families[mask], language_labels
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        default="model_artifacts/v1",
        help="saved training run or published model_artifacts/v1 directory",
    )
    args = parser.parse_args()
    print(json.dumps(evaluate(_path(args.run_dir)), indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
