"""V1 model loader: window-pooled CodeBERT embeddings + calibrated XGBoost heads.

The registry imports this module only when a model of kind "v1" is loaded, so scikit-learn
and xgboost are not imported at startup.

It reads the folder that scripts.training.v1_pipeline saves:

    model_artifacts/<entry.path>/
        preprocessing.joblib   {"calibrator", "threshold", "cwe_classes"}
        binary_model.json      XGBoost binary model
        cwe_model.json         XGBoost CWE model
        config.json            CodeBERT model and windowing configuration

models.yaml entry that uses it:

    - version: v1
      kind: v1
      languages: [python, cpp]     # both supported languages use V1
      path: v1                     # a folder inside model_artifacts/

Inference uses the same window splitting and mean pooling as training.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shield_core.models.registry import ModelEntry, ModelLoadError

SUPPORTED_FEATURES = "codebert_window_embeddings"
OTHER_CWE = "Other"  # the catch-all class from train_v1.py; it is not a real CWE id


class V1Model:
    """Answers predict(code, language) with a Result. Built by load(), not by hand."""

    def __init__(
        self,
        version: str,
        calibrator: Any,
        threshold: float,
        binary: Any,
        cwe_model: Any | None,
        cwe_classes: list[str],
        embedding_config: dict[str, Any],
        calibrators_by_language: dict[str, Any] | None = None,
        thresholds_by_language: dict[str, float] | None = None,
        family_model: Any | None = None,
        family_classes: list[str] | None = None,
        family_constant: int | None = None,
        leaf_heads: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.version = version
        self._calibrator = calibrator
        self._threshold = float(threshold)
        self._calibrators_by_language = calibrators_by_language or {}
        self._thresholds_by_language = thresholds_by_language or {}
        self._binary = binary
        self._cwe_model = cwe_model
        self._cwe_classes = list(cwe_classes)
        self._family_model = family_model
        self._family_classes = list(family_classes or [])
        self._family_constant = family_constant
        self._leaf_heads = leaf_heads or {}
        self._embedding_config = embedding_config
        self._embedder = None

    def predict(self, code: str, language: str):
        import contextlib
        import io

        from shield_core.interface import Finding, Result

        if not code or not code.strip():
            # nothing to analyse: same answer as the stub, no crash
            return Result(vulnerable=False, cwe=None, confidence=0.0, model_version=self.version)

        with contextlib.redirect_stdout(io.StringIO()):
            if self._embedder is None:
                from scripts.training.v1_pipeline import _embedder

                self._embedder = _embedder({"embedding": self._embedding_config})
            import pandas as pd

            from scripts.embeddings.long_embedding import process_dataset

            _, features = process_dataset(
                pd.DataFrame({"code": [code]}),
                self._embedder,
                overlap=int(self._embedding_config.get("overlap", 64)),
                max_tokens=int(self._embedding_config.get("max_tokens", 512)),
            )
        features = features.astype("float32", copy=False)
        raw = float(self._binary.predict_proba(features)[0, 1])
        calibrator = self._calibrators_by_language.get(language, self._calibrator)
        threshold = self._thresholds_by_language.get(language, self._threshold)
        p_vulnerable = float(calibrator.predict([raw])[0])  # calibrated probability
        vulnerable = p_vulnerable >= threshold

        cwe = None
        if vulnerable and (self._family_model is not None or self._family_constant is not None):
            family_id = self._family_constant
            if family_id is None:
                family_id = int(self._family_model.predict(features)[0])
            if 0 <= family_id < len(self._family_classes):
                family = self._family_classes[family_id]
                leaf = self._leaf_heads.get(family, {})
                if "constant" in leaf and leaf["constant"] is not None:
                    label = leaf["constant"]
                elif leaf.get("model") is not None:
                    label_id = int(leaf["model"].predict(features)[0])
                    label = leaf["classes"][label_id]
                else:
                    label = OTHER_CWE
            else:
                label = OTHER_CWE
            cwe = None if label == OTHER_CWE else label
        elif vulnerable and self._cwe_model is not None:
            label = self._cwe_classes[int(self._cwe_model.predict(features)[0])]
            cwe = None if label == OTHER_CWE else label

        # confidence = how sure the model is about the answer it gives
        confidence = p_vulnerable if vulnerable else 1.0 - p_vulnerable
        findings = (
            [Finding(cwe=cwe, confidence=float(confidence), language=language)] if cwe else []
        )
        return Result(
            vulnerable=bool(vulnerable),
            cwe=cwe,
            confidence=float(confidence),
            findings=findings,
            model_version=self.version,
        )


def _read_model(folder: Path, stem: str, required: bool) -> Any | None:
    json_path = folder / f"{stem}.json"
    joblib_path = folder / f"{stem}.joblib"
    if json_path.exists():
        from xgboost import XGBClassifier

        model = XGBClassifier()
        model.load_model(str(json_path))
        return model
    if joblib_path.exists():
        import joblib

        return joblib.load(joblib_path)
    if required:
        raise ModelLoadError(f"V1: neither {json_path.name} nor {joblib_path.name} in {folder}")
    return None


def load(entry: ModelEntry, artifact_dir: Path) -> V1Model:
    """Loader for models.yaml entries with kind: v1."""
    if entry.path is None:
        raise ModelLoadError(f"model {entry.version}: kind 'v1' needs a 'path' (a folder)")
    folder = Path(artifact_dir) / entry.path
    if not folder.is_dir():
        raise ModelLoadError(f"model {entry.version}: folder not found: {folder}")

    config_file = folder / "config.json"
    if config_file.exists():
        features = json.loads(config_file.read_text(encoding="utf-8")).get("features", None)
        if features != SUPPORTED_FEATURES:
            raise ModelLoadError(
                f"model {entry.version}: trained with features {features!r}; "
                f"this loader only supports {SUPPORTED_FEATURES!r}"
            )

    prep_file = folder / "preprocessing.joblib"
    if not prep_file.exists():
        raise ModelLoadError(f"model {entry.version}: missing {prep_file.name} in {folder}")
    import joblib

    prep = joblib.load(prep_file)
    missing = [k for k in ("calibrator", "threshold", "cwe_classes") if k not in prep]
    if missing:
        raise ModelLoadError(f"model {entry.version}: {prep_file.name} lacks: {', '.join(missing)}")

    leaf_heads = {}
    for family, descriptor in prep.get("leaf_heads", {}).items():
        leaf_model = (
            _read_model(folder, Path(descriptor["file"]).stem, required=False)
            if descriptor.get("file")
            else None
        )
        leaf_heads[family] = {
            "classes": descriptor.get("classes", []),
            "constant": descriptor.get("constant"),
            "model": leaf_model,
        }
    family_model = _read_model(folder, "family_model", required=False)
    return V1Model(
        version=entry.version,
        calibrator=prep["calibrator"],
        threshold=prep["threshold"],
        binary=_read_model(folder, "binary_model", required=True),
        cwe_model=_read_model(folder, "cwe_model", required=False),
        cwe_classes=prep["cwe_classes"],
        embedding_config=json.loads(config_file.read_text(encoding="utf-8")).get(
            "embedding", {"model_name": "microsoft/codebert-base", "max_tokens": 512, "overlap": 64}
        ),
        calibrators_by_language=prep.get("calibrators_by_language"),
        thresholds_by_language=prep.get("thresholds_by_language"),
        family_model=family_model,
        family_classes=prep.get("family_classes"),
        family_constant=prep.get("family_constant"),
        leaf_heads=leaf_heads,
    )
