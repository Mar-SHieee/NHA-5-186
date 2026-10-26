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
      languages: [python]          # only what V1 was trained on
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
    ) -> None:
        self.version = version
        self._calibrator = calibrator
        self._threshold = float(threshold)
        self._binary = binary
        self._cwe_model = cwe_model
        self._cwe_classes = list(cwe_classes)
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
        p_vulnerable = float(self._calibrator.predict([raw])[0])  # calibrated probability
        vulnerable = p_vulnerable >= self._threshold

        cwe = None
        if vulnerable and self._cwe_model is not None:
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
    )
