from __future__ import annotations

import numpy as np
import pytest

from shield_core.models.registry import ModelEntry, ModelLoadError
from shield_core.models.v1 import V1Model, load


class Binary:
    def predict_proba(self, x):
        return np.array([[0.1, 0.9]])


class Cwe:
    def predict(self, x):
        return np.array([0])


class Calibrator:
    def predict(self, values):
        return np.asarray(values)


def test_codebert_artifact_predicts_cwe_and_confidence(monkeypatch):
    import scripts.embeddings.long_embedding as embedding_script
    import scripts.training.v1_pipeline as pipeline

    monkeypatch.setattr(pipeline, "_embedder", lambda config: object())
    monkeypatch.setattr(
        embedding_script,
        "process_dataset",
        lambda df, embedder, **kwargs: (df, np.ones((len(df), 768), dtype=np.float32)),
    )
    model = V1Model(
        "v1",
        Calibrator(),
        0.5,
        Binary(),
        Cwe(),
        ["CWE-89"],
        {"model_name": "microsoft/codebert-base", "max_tokens": 512, "overlap": 64},
    )
    result = model.predict("cursor.execute(sql)", "python")
    assert result.vulnerable is True
    assert result.cwe == "CWE-89"
    assert result.confidence == pytest.approx(0.9)
    assert result.model_version == "v1"


def test_empty_code_does_not_load_embedder():
    model = V1Model("v1", Calibrator(), 0.5, Binary(), None, [], {})
    result = model.predict("  ", "python")
    assert result.vulnerable is False
    assert result.confidence == 0.0


def test_loader_rejects_old_tfidf_artifacts(tmp_path):
    folder = tmp_path / "v1"
    folder.mkdir()
    (folder / "config.json").write_text('{"features":"tfidf"}', encoding="utf-8")
    entry = ModelEntry("v1", "v1", ("python",), path="v1")
    with pytest.raises(ModelLoadError, match="codebert_window_embeddings"):
        load(entry, tmp_path)
