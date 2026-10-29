"""Train/evaluate the CodeBERT-embedding + XGBoost V1 and save deployable runs."""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    f1_score,
    matthews_corrcoef,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG: dict[str, Any] = {
    "seed": 42,
    "manifest": "docs/datasets/audits/dataset_manifest_v0.json",
    "assignment_file": None,
    "splits_dir": "data/interim/splits",
    "language": "python",
    "use_fixed_code_as_negatives": True,
    "min_cwe_count": 20,
    "binary_target_recall": None,
    "binary_threshold_metric": "precision_recall_balance",
    "xgb": {
        "n_estimators": 1000,
        "learning_rate": 0.05,
        "max_depth": 6,
        "subsample": 0.8,
        "colsample_bytree": 0.7,
        "reg_lambda": 1.0,
        "early_stopping_rounds": 75,
    },
    "embedding": {"model_name": "microsoft/codebert-base", "max_tokens": 512, "overlap": 64},
}


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def first_cwe(value: Any) -> str | None:
    if isinstance(value, str):
        values = [value]
    elif value is None:
        values = []
    else:
        values = list(value)
    return next((str(item) for item in values if str(item).startswith("CWE-")), None)


def load_split(
    path: Path, language: str, use_fixed: bool, *, require_code: bool = True
) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(
            f"Split file is missing: {path}. Build/freeze the split manifest first."
        )
    df = pd.read_parquet(path)
    required = {"language", "label", "cwe"}
    if require_code:
        required.add("code")
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path.name} lacks required columns: {sorted(missing)}")
    if language != "all":
        df = df[df.language == language].copy()
    else:
        df = df.copy()
    df["cwe_all"] = df.cwe.map(
        lambda v: [v] if isinstance(v, str) else list(v) if v is not None else []
    )
    df["cwe"] = df.cwe.map(first_cwe)
    if use_fixed and "code" in df and "fixed_code" in df:
        fixed = df[(df.label == 1) & df.fixed_code.notna() & (df.fixed_code != df.code)].copy()
        fixed["code"], fixed["label"], fixed["cwe"] = fixed.fixed_code, 0, None
        fixed["cwe_all"] = [[] for _ in range(len(fixed))]
        df = pd.concat([df, fixed], ignore_index=True)
    if "code" in df:
        df["code"] = df.code.fillna("").astype(str)
    df["label"] = df.label.astype(int)
    if "code" in df:
        df = df[df.code.str.strip().ne("")].drop_duplicates("code").reset_index(drop=True)
    if df.label.nunique() < 2:
        raise ValueError(f"{path.name} has only one class for language {language!r}")
    return df


def load_precomputed_split(
    metadata_path: Path,
    embedding_path: Path,
    language: str,
    assignment_path: Path | None = None,
    split: str | None = None,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Filter metadata and vectors together while retaining their original row alignment."""
    frame = pd.read_parquet(metadata_path)
    required = {"language", "label", "cwe"}
    if not required.issubset(frame.columns):
        raise ValueError(f"{metadata_path.name} needs metadata columns: {sorted(required)}")
    vectors = np.load(embedding_path, mmap_mode="r", allow_pickle=False)
    if vectors.ndim != 2 or len(vectors) != len(frame):
        raise ValueError(
            f"Embedding/metadata row mismatch: {len(vectors)} vectors in {embedding_path}, "
            f"{len(frame)} rows in {metadata_path}."
        )
    if not np.isfinite(vectors).all():
        raise ValueError(f"Non-finite embedding values in {embedding_path}")
    if assignment_path and split:
        verify_assignment_order(frame, assignment_path, split)

    keep = (
        np.ones(len(frame), dtype=bool)
        if language == "all"
        else frame["language"].eq(language).to_numpy()
    )
    row_indices = np.flatnonzero(keep)
    frame = frame.loc[keep].copy()
    if "code" in frame:
        frame["code"] = frame.code.fillna("").astype(str)
        keep_code = frame.code.str.strip().ne("").to_numpy()
        frame, row_indices = frame.loc[keep_code], row_indices[keep_code]
        keep_unique = ~frame.code.duplicated().to_numpy()
        frame, row_indices = frame.loc[keep_unique], row_indices[keep_unique]
    frame["cwe_all"] = frame.cwe.map(
        lambda v: [v] if isinstance(v, str) else list(v) if v is not None else []
    )
    frame["cwe"] = frame.cwe.map(first_cwe)
    frame["label"] = frame.label.astype(int)
    if frame.label.nunique() < 2:
        raise ValueError(f"{metadata_path.name} has only one class for {language!r}")
    return frame.reset_index(drop=True), np.asarray(vectors[row_indices], dtype=np.float32)


def verify_assignment_order(frame: pd.DataFrame, assignment_path: Path, split: str) -> None:
    assignments = pd.read_parquet(assignment_path)
    required = {"row_id", "split", "commit_key"}
    if not required.issubset(assignments.columns):
        raise ValueError(f"{assignment_path.name} needs columns: {sorted(required)}")
    rows = assignments.loc[assignments.split.eq(split)].sort_values("row_id").reset_index(drop=True)
    if len(rows) != len(frame):
        raise ValueError(
            f"{split} assignment count {len(rows)} does not match metadata row count {len(frame)}"
        )
    if "commit" not in frame:
        raise ValueError("Metadata needs a commit column to verify assignment order")
    metadata_commits = frame.commit.fillna("").astype(str).str.lower().to_numpy()
    assignment_commits = rows.commit_key.fillna("").astype(str).str.lower().to_numpy()
    comparable = (metadata_commits != "") & (assignment_commits != "")
    if not np.array_equal(metadata_commits[comparable], assignment_commits[comparable]):
        raise ValueError(f"{split} parquet order does not match {assignment_path.name}")


def _embedder(config: dict[str, Any]):
    sys.path.insert(0, str(ROOT))
    from shield_core.embeddings.embedder import CodeBERTEmbedder

    return CodeBERTEmbedder(
        model_name=config["embedding"]["model_name"],
        cache_dir=str(ROOT / "data" / "cache"),
        max_tokens=int(config["embedding"]["max_tokens"]),
    )


def embedding_matrix(df: pd.DataFrame, split: str, config: dict[str, Any], embedder) -> np.ndarray:
    # Cache by content and embedder settings, not by split, so v0/v1 and later runs
    # reuse the same frozen CodeBERT vectors.
    import hashlib

    from scripts.embeddings.long_embedding import process_dataset

    cache_dir = _path("data/interim/v1_embeddings/codebert")
    cache_dir.mkdir(parents=True, exist_ok=True)
    codes = df.code.tolist()
    model_id = ":".join(
        str(config["embedding"][key]) for key in ("model_name", "max_tokens", "overlap")
    )
    keys = [
        hashlib.sha256((model_id + "\0" + code).encode("utf-8", "ignore")).hexdigest()
        for code in codes
    ]
    result = np.empty((len(codes), 768), dtype=np.float32)
    grouped: dict[str, list[int]] = {}
    for index, key in enumerate(keys):
        grouped.setdefault(key[:2], []).append(index)
    for bucket, indices in grouped.items():
        cache_path = cache_dir / f"{bucket}.npz"
        cached: dict[str, np.ndarray] = {}
        if cache_path.exists():
            with np.load(cache_path, allow_pickle=False) as stored:
                cached = {
                    key: vector
                    for key, vector in zip(stored["keys"].tolist(), stored["vectors"], strict=True)
                }
        missing_codes, missing_keys = [], []
        for index in indices:
            key = keys[index]
            if key in cached:
                result[index] = cached[key]
            elif key not in missing_keys:
                missing_codes.append(codes[index])
                missing_keys.append(key)
        if missing_codes:
            _, vectors = process_dataset(
                pd.DataFrame({"code": missing_codes}),
                embedder,
                overlap=int(config["embedding"]["overlap"]),
                max_tokens=int(config["embedding"]["max_tokens"]),
            )
            if not np.isfinite(vectors).all():
                raise ValueError(f"Non-finite embedding values in {split}")
            for key, vector in zip(missing_keys, vectors, strict=True):
                cached[key] = vector.astype(np.float32, copy=False)
            np.savez_compressed(
                cache_path, keys=np.asarray(list(cached)), vectors=np.stack(list(cached.values()))
            )
            for index in indices:
                result[index] = cached[keys[index]]
    return result


def _model(params: dict[str, Any], seed: int, classes: int | None = None) -> XGBClassifier:
    options = dict(params)
    early_stopping_rounds = int(options.pop("early_stopping_rounds", 75))
    if classes:
        objective, metric = "multi:softprob", "mlogloss"
        options["num_class"] = classes
    else:
        objective, metric = "binary:logistic", "logloss"
    return XGBClassifier(
        **options,
        objective=objective,
        eval_metric=metric,
        random_state=seed,
        n_jobs=-1,
        tree_method="hist",
        early_stopping_rounds=early_stopping_rounds,
    )


def _fit(model, x, y, xv, yv, params, sample_groups=None):
    options = {
        "sample_weight": compute_sample_weight(
            "balanced", y if sample_groups is None else sample_groups
        ),
        "verbose": 50 if len(y) >= 100_000 else 20 if len(y) >= 10_000 else False,
    }
    if len(np.unique(yv)) > 1:
        options["eval_set"] = [(xv, yv)]
    else:
        model.set_params(early_stopping_rounds=None)
    return model.fit(x, y, **options)


def _binary_metrics(y: np.ndarray, p: np.ndarray, threshold: float | np.ndarray) -> dict[str, Any]:
    pred = (p >= threshold).astype(int)
    precision = float(precision_score(y, pred, zero_division=0))
    recall = float(recall_score(y, pred, zero_division=0))
    return {
        "roc_auc": float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else None,
        "pr_auc": float(average_precision_score(y, p)),
        "precision": precision,
        "recall": recall,
        "precision_recall_balance": min(precision, recall),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "mcc": float(matthews_corrcoef(y, pred)),
        "brier": float(brier_score_loss(y, p)),
    }


def _metrics_by_language(
    frames: dict[str, pd.DataFrame],
    labels: dict[str, np.ndarray],
    probabilities: dict[str, np.ndarray],
    thresholds: float | dict[str, float],
) -> dict[str, dict[str, Any]]:
    results = {}
    for language in sorted(set().union(*(set(frame.language) for frame in frames.values()))):
        results[language] = {}
        for split, frame in frames.items():
            mask = frame.language.eq(language).to_numpy()
            results[language][split] = _binary_metrics(
                labels[split][mask],
                probabilities[split][mask],
                thresholds.get(language, 0.5) if isinstance(thresholds, dict) else thresholds,
            )
    return results


def _calibrate_by_language(
    raw,
    frame,
    labels,
    target_recall: float | None = None,
    metric: str = "f1",
):
    calibrators, thresholds, probabilities = {}, {}, np.empty(len(raw), dtype=np.float64)
    for language in sorted(frame.language.unique()):
        mask = frame.language.eq(language).to_numpy()
        calibrator = IsotonicRegression(out_of_bounds="clip").fit(raw[mask], labels[mask])
        calibrated = calibrator.predict(raw[mask])
        candidates = np.unique(calibrated)
        if target_recall is not None:
            if not 0 < float(target_recall) <= 1:
                raise ValueError("binary_target_recall must be in (0, 1]")
            eligible = [
                value
                for value in candidates
                if recall_score(labels[mask], calibrated >= value, zero_division=0)
                >= float(target_recall)
            ]
            # Highest feasible threshold meets the recall target with the fewest
            # predicted positives, and therefore favors precision within that constraint.
            threshold = float(max(eligible)) if eligible else float(min(candidates))
        else:
            if metric not in {"f1", "mcc", "precision_recall_balance"}:
                raise ValueError(
                    "binary_threshold_metric must be 'precision_recall_balance', 'f1', or 'mcc'"
                )

            language_labels = labels[mask]

            def objective(value, calibrated=calibrated, language_labels=language_labels):
                predictions = calibrated >= value
                if metric == "f1":
                    return f1_score(language_labels, predictions, zero_division=0)
                if metric == "mcc":
                    return matthews_corrcoef(language_labels, predictions)
                precision = precision_score(language_labels, predictions, zero_division=0)
                recall = recall_score(language_labels, predictions, zero_division=0)
                harmonic_mean = f1_score(language_labels, predictions, zero_division=0)
                return (min(precision, recall), harmonic_mean, -abs(precision - recall))

            threshold = float(max(candidates, key=objective))
        calibrators[language] = calibrator
        thresholds[language] = threshold
        probabilities[mask] = calibrated
    return calibrators, thresholds, probabilities


def _language_class_groups(frame, labels):
    return frame.language.astype(str).to_numpy() + "::" + np.asarray(labels).astype(str)


def _publish_run(run_dir: Path, destination: Path) -> None:
    import hashlib
    import shutil
    import zipfile

    destination.mkdir(parents=True, exist_ok=True)
    for stale in (
        *destination.glob("leaf_*.json"),
        *(
            destination / name
            for name in (
                "binary_model.json",
                "cwe_model.json",
                "family_model.json",
                "preprocessing.joblib",
                "config.json",
                "metrics.json",
                "calibration_plot_data.csv",
                "SHA256SUMS",
            )
        ),
    ):
        if stale.exists():
            stale.unlink()
    for source in run_dir.iterdir():
        if source.is_file():
            shutil.copy2(source, destination / source.name)
    files = sorted(
        path for path in destination.iterdir() if path.is_file() and path.name != "SHA256SUMS"
    )
    sums = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in files
    )
    (destination / "SHA256SUMS").write_text(sums, encoding="ascii")
    bundle = destination.parent / "shield-v1.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.name)
        archive.write(destination / "SHA256SUMS", "SHA256SUMS")
    print(f"Created installer bundle at {bundle}")


def run(config: dict[str, Any], *, publish: bool = False) -> Path:
    manifest_value = config.get("manifest")
    manifest_path = _path(manifest_value) if manifest_value else None
    if manifest_path and not manifest_path.is_file():
        raise FileNotFoundError(f"Split manifest is missing: {manifest_path}")
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path
        else {"manifest_version": "external-precomputed-inputs", "dataset_hash": None}
    )
    splits = _path(config["splits_dir"])
    precomputed = config.get("embedding_files")
    if precomputed:
        loaded = {
            name: load_precomputed_split(
                splits / f"{name}.parquet",
                _path(precomputed[name]),
                config["language"],
                _path(config["assignment_file"]) if config.get("assignment_file") else None,
                name,
            )
            for name in ("train", "val", "test")
        }
        data = {name: part[0] for name, part in loaded.items()}
        matrices = {name: part[1] for name, part in loaded.items()}
    else:
        data = {
            name: load_split(
                splits / f"{name}.parquet",
                config["language"],
                config["use_fixed_code_as_negatives"],
            )
            for name in ("train", "val", "test")
        }
    # Guard against duplicate function text crossing partitions independently of split QA.
    if all("code" in frame for frame in data.values()):
        train_codes = set(data["train"].code)
        val_keep = ~data["val"].code.isin(train_codes)
        data["val"] = data["val"][val_keep].reset_index(drop=True)
        if precomputed:
            matrices["val"] = matrices["val"][val_keep.to_numpy()]
        val_codes = set(data["val"].code)
        test_keep = ~data["test"].code.isin(train_codes | val_codes)
        data["test"] = data["test"][test_keep].reset_index(drop=True)
        if precomputed:
            matrices["test"] = matrices["test"][test_keep.to_numpy()]
    if any(frame.empty for frame in data.values()):
        raise ValueError(
            "Train, validation, and test each need rows after language and leakage filtering"
        )
    print(
        "Using rows by split/language: "
        + json.dumps(
            {
                split: frame.language.value_counts().sort_index().astype(int).to_dict()
                for split, frame in data.items()
            }
        ),
        flush=True,
    )

    if not precomputed:
        embedder = _embedder(config)
        matrices = {name: embedding_matrix(df, name, config, embedder) for name, df in data.items()}
    y = {name: df.label.to_numpy(dtype=np.int32) for name, df in data.items()}
    print(f"Fitting binary head on {len(y['train']):,} training rows", flush=True)
    binary_groups = (
        _language_class_groups(data["train"], y["train"])
        if config.get("balance_languages", False)
        else None
    )
    binary = _fit(
        _model(config["xgb"], config["seed"]),
        matrices["train"],
        y["train"],
        matrices["val"],
        y["val"],
        config["xgb"],
        binary_groups,
    )
    val_raw = binary.predict_proba(matrices["val"])[:, 1]
    test_raw = binary.predict_proba(matrices["test"])[:, 1]
    calibrator = IsotonicRegression(out_of_bounds="clip").fit(val_raw, y["val"])
    val_prob, test_prob = calibrator.predict(val_raw), calibrator.predict(test_raw)
    thresholds = np.unique(np.quantile(val_prob, np.linspace(0.01, 0.99, 99)))
    threshold = float(max(thresholds, key=lambda t: matthews_corrcoef(y["val"], val_prob >= t)))
    language_calibrators, language_thresholds, val_language_prob = _calibrate_by_language(
        val_raw,
        data["val"],
        y["val"],
        config.get("binary_target_recall"),
        config.get("binary_threshold_metric", "f1"),
    )
    test_language_prob = np.empty(len(test_raw), dtype=np.float64)
    for language, language_calibrator in language_calibrators.items():
        mask = data["test"].language.eq(language).to_numpy()
        test_language_prob[mask] = language_calibrator.predict(test_raw[mask])
    val_thresholds = data["val"].language.map(language_thresholds).to_numpy(dtype=np.float64)
    test_thresholds = data["test"].language.map(language_thresholds).to_numpy(dtype=np.float64)
    validation_metrics = _binary_metrics(y["val"], val_language_prob, val_thresholds)
    binary_metrics = _binary_metrics(y["test"], test_language_prob, test_thresholds)
    language_metrics = {
        "validation": _metrics_by_language(
            {"validation": data["val"]},
            {"validation": y["val"]},
            {"validation": val_language_prob},
            language_thresholds,
        ),
        "test": _metrics_by_language(
            {"test": data["test"]},
            {"test": y["test"]},
            {"test": test_language_prob},
            language_thresholds,
        ),
    }

    # Hierarchical CWE head: predict a broad internal family, then classify the CWE
    # within that family. The API still returns a real CWE ID or None.
    family_map_path = _path(config.get("cwe_family_map", "scripts/training/cwe_family_map.json"))
    family_spec = json.loads(family_map_path.read_text(encoding="utf-8"))
    cwe_to_family = family_spec["cwe_to_family"]
    fallback_family = family_spec.get("fallback_family", "other")
    cwe_train_mask = (y["train"] == 1) & data["train"].cwe.notna().to_numpy()
    cwe_val_mask = (y["val"] == 1) & data["val"].cwe.notna().to_numpy()
    cwe_test_mask = (y["test"] == 1) & data["test"].cwe.notna().to_numpy()
    if cwe_train_mask.sum() == 0:
        raise ValueError("No labeled vulnerable training rows are available for the CWE heads")
    for split in data:
        data[split]["cwe_family"] = data[split].cwe.map(
            lambda cwe: cwe_to_family.get(cwe, fallback_family) if isinstance(cwe, str) else None
        )
    cwe_params = config.get("cwe_xgb", config["xgb"])
    family_names = sorted(data["train"].loc[cwe_train_mask, "cwe_family"].dropna().unique())
    family_ids = {name: idx for idx, name in enumerate(family_names)}

    def fit_multiclass_head(train_x, train_labels, val_x, val_labels, groups=None):
        classes = sorted(set(train_labels.tolist()))
        if len(classes) == 1:
            return {"constant": classes[0], "classes": classes}
        remap = {label: i for i, label in enumerate(classes)}
        ytr = np.asarray([remap[item] for item in train_labels], dtype=np.int32)
        yva = np.asarray([remap.get(item, 0) for item in val_labels], dtype=np.int32)
        model = _fit(
            _model(cwe_params, config["seed"], len(classes)),
            train_x,
            ytr,
            val_x,
            yva,
            cwe_params,
            groups,
        )
        return {"model": model, "classes": classes}

    family_train = data["train"].loc[cwe_train_mask, "cwe_family"].map(family_ids).to_numpy()
    family_val_mask = cwe_val_mask & data["val"].cwe_family.isin(family_ids).to_numpy()
    family_val = data["val"].loc[family_val_mask, "cwe_family"].map(family_ids).to_numpy()
    family_groups = (
        _language_class_groups(data["train"].loc[cwe_train_mask], family_train)
        if config.get("balance_languages", False)
        else None
    )
    family_head = fit_multiclass_head(
        matrices["train"][cwe_train_mask],
        family_train,
        matrices["val"][family_val_mask],
        family_val,
        family_groups,
    )
    min_count = int(config["min_cwe_count"])
    leaf_heads = {}
    leaf_labels = {}
    train_cwes = data["train"].loc[cwe_train_mask, "cwe"]
    supported = set(train_cwes.value_counts().loc[lambda counts: counts >= min_count].index)
    for family in family_names:
        fam_train_mask = cwe_train_mask & data["train"].cwe_family.eq(family).to_numpy()
        fam_val_mask = cwe_val_mask & data["val"].cwe_family.eq(family).to_numpy()
        raw_train = (
            data["train"]
            .loc[fam_train_mask, "cwe"]
            .map(lambda cwe: cwe if cwe in supported else "Other")
            .to_numpy()
        )
        raw_val = (
            data["val"]
            .loc[fam_val_mask, "cwe"]
            .map(lambda cwe: cwe if cwe in supported else "Other")
            .to_numpy()
        )
        groups = (
            _language_class_groups(data["train"].loc[fam_train_mask], raw_train)
            if config.get("balance_languages", False)
            else None
        )
        leaf_heads[family] = fit_multiclass_head(
            matrices["train"][fam_train_mask],
            raw_train,
            matrices["val"][fam_val_mask],
            raw_val,
            groups,
        )
        leaf_labels[family] = leaf_heads[family]["classes"]

    def predict_head(head, features):
        if "constant" in head:
            return np.repeat(head["constant"], len(features))
        ids = head["model"].predict_proba(features).argmax(axis=1)
        return np.asarray(head["classes"], dtype=object)[ids]

    def predict_hierarchical(features):
        family_pred = predict_head(family_head, features).astype(int)
        labels = np.full(len(features), "Other", dtype=object)
        for family, family_id in family_ids.items():
            mask = family_pred == family_id
            if mask.any():
                labels[mask] = predict_head(leaf_heads[family], features[mask])
        return labels

    test_rows = data["test"].loc[cwe_test_mask]
    true_test_cwes = test_rows.cwe.map(lambda cwe: cwe if cwe in supported else "Other").to_numpy()
    pred_cwes = (
        predict_hierarchical(matrices["test"][cwe_test_mask])
        if cwe_test_mask.any()
        else np.array([])
    )
    cwe_metrics = {}
    cwe_language_metrics = {}
    if len(true_test_cwes):
        cwe_metrics = {
            "accuracy": float(accuracy_score(true_test_cwes, pred_cwes)),
            "macro_f1": float(
                f1_score(true_test_cwes, pred_cwes, average="macro", zero_division=0)
            ),
            "weighted_f1": float(
                f1_score(true_test_cwes, pred_cwes, average="weighted", zero_division=0)
            ),
            "support": int(len(true_test_cwes)),
            "classes": int(len(set(true_test_cwes))),
        }
        langs = test_rows.language.to_numpy()
        for language in sorted(set(langs)):
            mask = langs == language
            cwe_language_metrics[language] = {
                "accuracy": float(accuracy_score(true_test_cwes[mask], pred_cwes[mask])),
                "macro_f1": float(
                    f1_score(
                        true_test_cwes[mask], pred_cwes[mask], average="macro", zero_division=0
                    )
                ),
                "weighted_f1": float(
                    f1_score(
                        true_test_cwes[mask], pred_cwes[mask], average="weighted", zero_division=0
                    )
                ),
                "support": int(mask.sum()),
            }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = _path(f"model_artifacts/train_runs/xgboost_codebert_v1_{stamp}")
    run_dir.mkdir(parents=True, exist_ok=False)
    binary.save_model(str(run_dir / "binary_model.json"))
    if "model" in family_head:
        family_head["model"].save_model(str(run_dir / "family_model.json"))
    leaf_model_classes = {}
    for idx, family in enumerate(family_names):
        head = leaf_heads[family]
        if "model" in head:
            filename = f"leaf_{idx}.json"
            head["model"].save_model(str(run_dir / filename))
            leaf_model_classes[family] = filename
    import joblib

    joblib.dump(
        {
            "calibrator": calibrator,
            "threshold": threshold,
            "calibrators_by_language": language_calibrators,
            "thresholds_by_language": language_thresholds,
            "cwe_classes": [],
            "family_classes": family_names,
            "family_constant": family_head.get("constant"),
            "leaf_heads": {
                family: {
                    "classes": leaf_heads[family]["classes"],
                    "constant": leaf_heads[family].get("constant"),
                    "file": leaf_model_classes.get(family),
                }
                for family in family_names
            },
        },
        run_dir / "preprocessing.joblib",
    )
    config["features"] = "codebert_window_embeddings"
    config["manifest_hash"] = manifest.get("dataset_hash")
    config["manifest_version"] = manifest.get("manifest_version")
    input_files = {
        **{f"metadata_{name}": splits / f"{name}.parquet" for name in data},
    }
    if precomputed:
        input_files.update(
            {f"embeddings_{name}": _path(path) for name, path in precomputed.items()}
        )
    if config.get("assignment_file"):
        input_files["assignments"] = _path(config["assignment_file"])
    from shield_core.tracking import hash_file

    config["input_hashes"] = {name: hash_file(path) for name, path in input_files.items()}
    (run_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    scores = {
        "binary_validation": validation_metrics,
        "binary_test": binary_metrics,
        "threshold": threshold,
        "thresholds_by_language": language_thresholds,
        "binary_target_recall": config.get("binary_target_recall"),
        "binary_threshold_metric": config.get("binary_threshold_metric", "f1"),
        "cwe_test": cwe_metrics,
        "binary_by_language": language_metrics,
        "cwe_test_by_language": cwe_language_metrics,
        "rows": {k: len(v) for k, v in data.items()},
        "rows_by_language": {
            split: frame.language.value_counts().sort_index().astype(int).to_dict()
            for split, frame in data.items()
        },
        "cwe_classes": sorted(supported),
        "families": family_names,
    }
    (run_dir / "metrics.json").write_text(
        json.dumps(scores, indent=2, allow_nan=False), encoding="utf-8"
    )
    # Row-level test predictions for the per-CWE table (W2-P3-03)
    test_frame = data["test"]
    pred_label = (test_language_prob >= test_thresholds).astype(int)
    predictions = pd.DataFrame(
        {
            "language": test_frame.language.to_numpy(),
            "commit": test_frame["commit"].to_numpy() if "commit" in test_frame else None,
            "label": y["test"],
            "cwe_all": test_frame.cwe_all.to_numpy(),
            "pred_label": pred_label,
            "pred_cwe": predict_hierarchical(matrices["test"]),
        }
    )
    predictions.to_parquet(run_dir / "predictions_test.parquet", index=False)

    bins = np.clip((test_prob * 10).astype(int), 0, 9)
    (
        pd.DataFrame({"bin": bins, "pred": test_prob, "true": y["test"]})
        .groupby("bin")
        .agg(
            count=("true", "size"),
            mean_predicted=("pred", "mean"),
            fraction_positive=("true", "mean"),
        )
        .to_csv(run_dir / "calibration_plot_data.csv")
    )
    summary = {
        "binary_validation": scores["binary_validation"],
        "binary_test": scores["binary_test"],
        "cwe_test": {k: v for k, v in scores["cwe_test"].items() if k != "per_cwe"},
        "cwe_test_by_language": scores["cwe_test_by_language"],
        "rows": scores["rows"],
        "rows_by_language": scores["rows_by_language"],
        "binary_by_language": scores["binary_by_language"],
    }
    print(json.dumps(summary, indent=2, allow_nan=False))

    if publish:
        v1_dir = _path("model_artifacts/v1")
        _publish_run(run_dir, v1_dir)
        print(f"Published registry artifact to {v1_dir}")
    try:
        import mlflow

        mlflow.set_tracking_uri(f"sqlite:///{(_path('mlflow.db')).as_posix()}")
        mlflow.set_experiment("W2-P3-01_codebert_xgboost_v1")
        with mlflow.start_run(run_name=run_dir.name):
            mlflow.log_params(
                {
                    "seed": config["seed"],
                    "manifest_version": config["manifest_version"],
                    **config["xgb"],
                    **{f"cwe_{k}": v for k, v in config.get("cwe_xgb", {}).items()},
                }
            )
            mlflow.log_metrics(
                {
                    f"binary_{k}": v
                    for k, v in binary_metrics.items()
                    if v is not None and np.isfinite(v)
                }
            )
            mlflow.log_metrics(
                {f"cwe_{k}": v for k, v in cwe_metrics.items() if isinstance(v, (int, float))}
            )
            mlflow.log_artifacts(str(run_dir))
    except ImportError:
        print("MLflow is not installed; artifact and metrics were saved locally.")
    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="JSON config overrides")
    parser.add_argument(
        "--grid", help="JSON object of XGBoost param -> list of values; runs full Cartesian grid"
    )
    parser.add_argument(
        "--grid-file", help="path to a JSON file containing XGBoost parameter lists"
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="copy this run to model_artifacts/v1 for registry use",
    )
    args = parser.parse_args(argv)
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if args.config:
        overrides = json.loads(Path(args.config).read_text(encoding="utf-8"))
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(config.get(key), dict):
                config[key].update(value)
            else:
                config[key] = value
    if args.grid and args.grid_file:
        parser.error("pass either --grid or --grid-file, not both")
    grid = (
        json.loads(Path(args.grid_file).read_text(encoding="utf-8"))
        if args.grid_file
        else json.loads(args.grid)
        if args.grid
        else {}
    )
    keys = list(grid)
    trials = itertools.product(*(grid[k] for k in keys)) if keys else [()]
    best = None
    comparisons = []
    for values in trials:
        trial = json.loads(json.dumps(config))
        trial["xgb"].update(dict(zip(keys, values, strict=True)))
        print(f"Starting grid run with XGBoost parameters: {trial['xgb']}", flush=True)
        run_dir = run(trial, publish=False)
        scores = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
        saved_config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
        comparison = {
            "run": run_dir.name,
            **{f"xgb_{k}": v for k, v in saved_config["xgb"].items()},
        }
        comparison.update({f"val_{k}": v for k, v in scores["binary_validation"].items()})
        comparison.update({f"test_{k}": v for k, v in scores["binary_test"].items()})
        for split, languages in scores["binary_by_language"].items():
            comparison.update(
                {
                    f"{split}_{language}_{metric}": value
                    for language, metrics in languages.items()
                    for metric, value in metrics.items()
                }
            )
        comparison.update(
            {
                f"cwe_{k}": v
                for k, v in scores["cwe_test"].items()
                if k != "per_cwe" and isinstance(v, (int, float))
            }
        )
        comparisons.append(comparison)
        selection_metric = config.get("binary_threshold_metric", "f1")
        language_scores = [
            item["validation"][selection_metric]
            for item in scores["binary_by_language"]["validation"].values()
        ]
        selection_score = float(np.mean(language_scores))
        comparison[f"validation_macro_language_{selection_metric}"] = selection_score
        test_mcc = scores["binary_test"]["mcc"]
        print(
            f"Run: {run_dir} | macro validation {selection_metric}={selection_score:.4f} "
            f"| pooled test MCC={test_mcc:.4f}"
        )
        if best is None or selection_score > best[0]:
            best = (selection_score, run_dir)
    if best:
        print(f"Best validation score={best[0]:.4f}: {best[1]}")
        summary_path = _path("model_artifacts/train_runs/v1_grid_comparison.csv")
        pd.DataFrame(comparisons).to_csv(summary_path, index=False)
        print(f"Grid comparison: {summary_path}")
        if args.publish:
            destination = _path("model_artifacts/v1")
            _publish_run(best[1], destination)
            print(f"Published best validation run to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
