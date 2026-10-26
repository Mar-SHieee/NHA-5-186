import copy
import hashlib
import logging
import re

import pytest
import yaml

from shield_core import interface
from shield_core.interface import ModelUnavailableError, Result
from shield_core.models import registry
from shield_core.models.registry import (
    DEFAULT_CONFIG,
    ModelConfigError,
    ModelLoadError,
    ModelRegistry,
    StubModel,
    UnknownModelVersionError,
    load_config,
)

LOGGER = "shield_core.models.registry"


class FakeModel:
    def __init__(self, version):
        self.version = version

    def predict(self, code, language):
        return Result(vulnerable=True, cwe="CWE-89", confidence=0.9, model_version=self.version)


def load_fake(entry, artifact_dir):
    return FakeModel(entry.version)


def load_boom(entry, artifact_dir):
    raise ValueError("bad weights")


V1 = {"version": "v1", "kind": "fake", "languages": ["python", "cpp"]}
V2 = {"version": "v2", "kind": "fake", "languages": ["python"], "path": "v2/model.bin"}


@pytest.fixture(autouse=True)
def _fresh_default_registry(monkeypatch):
    monkeypatch.delenv(registry.CONFIG_ENV, raising=False)
    monkeypatch.delenv(registry.ARTIFACT_ENV, raising=False)
    registry.reload()
    yield
    registry.reload()


def write_config(tmp_path, models, default="v2", fallback="v1"):
    data = {"default": default, "fallback": fallback, "models": models}
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def make_registry(tmp_path, models=None, **config):
    cfg = write_config(tmp_path, models or [V1, V2], **config)
    kinds = {"fake": load_fake, "boom": load_boom}
    return ModelRegistry(cfg, tmp_path / "artifacts", kinds=kinds)


def put_artifact(tmp_path, name="v2/model.bin", data=b"weights"):
    file = tmp_path / "artifacts" / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(data)
    return file


# ------------------------------------------------------------------ choosing a model


def test_shipped_config_uses_v1_for_python_with_stub_fallback():
    config = load_config(DEFAULT_CONFIG)
    assert config.default == "v1"
    assert config.models["v1"].kind == "v1"
    assert config.models["v1"].languages == ("python",)
    assert config.fallback == "stub-v0"
    assert ModelRegistry(DEFAULT_CONFIG).get_model("cpp").version == "stub"


def test_default_model_is_used_when_it_loads(tmp_path):
    put_artifact(tmp_path)
    assert make_registry(tmp_path).get_model("python").version == "v2"


def test_language_without_a_configured_model_gets_the_stub(tmp_path):
    put_artifact(tmp_path)
    reg = make_registry(tmp_path, models=[{**V1, "languages": ["python"]}], default="v1")
    model = reg.get_model("cpp")
    assert isinstance(model, StubModel)
    assert model.version == "stub"


def test_default_that_does_not_list_the_language_falls_to_the_fallback(tmp_path):
    put_artifact(tmp_path)
    assert make_registry(tmp_path).get_model("cpp").version == "v1"


# ------------------------------------------------------------------ fallback


def test_removing_the_newer_model_falls_back_to_v1(tmp_path, caplog):
    file = put_artifact(tmp_path)
    assert make_registry(tmp_path).get_model("python").version == "v2"

    file.unlink()
    caplog.set_level(logging.WARNING, logger=LOGGER)
    model = make_registry(tmp_path).get_model("python")

    assert model.version == "v1"
    assert "file not found" in caplog.text
    assert "using v1 instead" in caplog.text


def test_corrupt_file_falls_back_to_v1(tmp_path):
    good = hashlib.sha256(b"weights").hexdigest()
    put_artifact(tmp_path, data=b"damaged")
    models = [V1, {**V2, "sha256": good}]
    assert make_registry(tmp_path, models=models).get_model("python").version == "v1"


def test_matching_checksum_loads_the_model(tmp_path):
    good = hashlib.sha256(b"weights").hexdigest()
    put_artifact(tmp_path)
    models = [V1, {**V2, "sha256": good}]
    assert make_registry(tmp_path, models=models).get_model("python").version == "v2"


def test_loader_that_raises_falls_back_to_v1(tmp_path):
    put_artifact(tmp_path)
    models = [V1, {**V2, "kind": "boom"}]
    assert make_registry(tmp_path, models=models).get_model("python").version == "v1"


def test_unknown_kind_falls_back_to_v1(tmp_path):
    put_artifact(tmp_path)
    models = [V1, {**V2, "kind": "does-not-exist"}]
    assert make_registry(tmp_path, models=models).get_model("python").version == "v1"


def test_missing_v1_too_is_an_error_not_a_silent_stub(tmp_path):
    models = [{**V1, "path": "v1/model.bin"}, V2]
    with pytest.raises(ModelLoadError, match="no model could be loaded"):
        make_registry(tmp_path, models=models).get_model("python")


def test_failed_load_is_remembered_until_reload(tmp_path):
    calls = []

    def counting_boom(entry, artifact_dir):
        calls.append(entry.version)
        raise ValueError("bad")

    cfg = write_config(tmp_path, [{**V1, "kind": "boom"}], default="v1")
    reg = ModelRegistry(cfg, tmp_path, kinds={"boom": counting_boom})
    for _ in range(3):
        with pytest.raises(ModelLoadError):
            reg.get_model("python")
    assert calls == ["v1"]


def test_loaded_model_is_cached(tmp_path):
    calls = []

    def counting(entry, artifact_dir):
        calls.append(entry.version)
        return FakeModel(entry.version)

    cfg = write_config(tmp_path, [V1], default="v1")
    reg = ModelRegistry(cfg, tmp_path, kinds={"fake": counting})
    assert reg.get_model("python") is reg.get_model("python")
    assert calls == ["v1"]


# ------------------------------------------------------------------ asking for a version


def test_specific_version_is_returned(tmp_path):
    put_artifact(tmp_path)
    assert make_registry(tmp_path).get_model("python", "v1").version == "v1"


def test_specific_version_that_fails_does_not_fall_back(tmp_path):
    with pytest.raises(ModelLoadError, match="file not found"):
        make_registry(tmp_path).get_model("python", "v2")


def test_unknown_version_raises(tmp_path):
    with pytest.raises(UnknownModelVersionError, match="v9"):
        make_registry(tmp_path).get_model("python", "v9")


def test_version_that_does_not_support_the_language_raises(tmp_path):
    put_artifact(tmp_path)
    with pytest.raises(UnknownModelVersionError, match="does not support"):
        make_registry(tmp_path).get_model("cpp", "v2")


# ------------------------------------------------------------------ the config rules

BASE = {
    "default": "v1",
    "fallback": "v1",
    "models": [{"version": "v1", "kind": "stub", "languages": ["python"]}],
}


def drop_key(key):
    def change(data):
        del data[key]

    return change


def set_value(*keys_and_value):
    *keys, value = keys_and_value

    def change(data):
        target = data
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value

    return change


def duplicate_version(data):
    data["models"].append(copy.deepcopy(data["models"][0]))


BAD_CONFIGS = [
    (drop_key("default"), "missing keys: default"),
    (set_value("extra", 1), "unknown keys: extra"),
    (set_value("default", "v9"), "'default' must name a version in 'models'"),
    (set_value("fallback", "v9"), "'fallback' must name a version in 'models'"),
    (set_value("models", []), "'models' must be a non-empty list"),
    (duplicate_version, "duplicate version"),
    (set_value("models", 0, "version", "stub"), "reserved"),
    (set_value("models", 0, "version", "V1"), "'version' must be"),
    (set_value("models", 0, "kind", ""), "'kind' must be a non-empty string"),
    (set_value("models", 0, "languages", []), "'languages' must be a non-empty list"),
    (set_value("models", 0, "languages", ["cobol"]), "unknown language"),
    (set_value("models", 0, "languages", ["python", "python"]), "duplicates"),
    (set_value("models", 0, "path", "/etc/model.bin"), "relative path"),
    (set_value("models", 0, "path", "../model.bin"), "relative path"),
    (set_value("models", 0, "path", "C:model.bin"), "relative path"),
    (set_value("models", 0, "sha256", "abc"), "'sha256' must be"),
    (set_value("models", 0, "options", "x"), "'options' must be a mapping"),
    (set_value("models", 0, "lang", "python"), "unknown keys: lang"),
]


@pytest.mark.parametrize(("change", "expected"), BAD_CONFIGS)
def test_broken_config_is_rejected_with_a_clear_message(tmp_path, change, expected):
    data = copy.deepcopy(BASE)
    change(data)
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ModelConfigError, match=re.escape(expected)) as info:
        load_config(path)
    assert "models.yaml" in str(info.value)


def test_entry_missing_a_required_key(tmp_path):
    data = copy.deepcopy(BASE)
    del data["models"][0]["kind"]
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ModelConfigError, match=re.escape("models[0]: missing keys: kind")):
        load_config(path)


def test_invalid_yaml_and_wrong_shape_and_missing_file(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("default: [unclosed\n", encoding="utf-8")
    with pytest.raises(ModelConfigError, match="invalid YAML"):
        load_config(bad)

    shape = tmp_path / "shape.yaml"
    shape.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ModelConfigError, match="mapping"):
        load_config(shape)

    with pytest.raises(ModelConfigError, match="cannot read"):
        load_config(tmp_path / "missing.yaml")


def test_the_shipped_config_is_valid():
    config = load_config(DEFAULT_CONFIG)
    assert config.default in config.models
    assert config.fallback in config.models


# ------------------------------------------------------------------ wiring into predict()


def test_predict_uses_the_registry_selected_model(monkeypatch):
    monkeypatch.setattr(interface.model_registry, "get_model", lambda language: FakeModel("v1"))
    result = interface.predict("x = 1", "python")
    assert result.model_version == "v1"
    assert result.vulnerable is True


def test_predict_uses_the_registry_and_stamps_the_model_version(monkeypatch):
    monkeypatch.setattr(interface.model_registry, "get_model", lambda language: FakeModel("v2"))
    result = interface.predict("x = 1", "python")
    assert result.model_version == "v2"
    assert result.cwe == "CWE-89"


def test_predict_turns_registry_errors_into_model_unavailable(monkeypatch):
    def broken(language):
        raise ModelLoadError("no model could be loaded")

    monkeypatch.setattr(interface.model_registry, "get_model", broken)
    with pytest.raises(ModelUnavailableError, match="no model could be loaded"):
        interface.predict("x = 1", "python")


def test_predict_turns_a_broken_config_into_model_unavailable(tmp_path, monkeypatch):
    bad = tmp_path / "models.yaml"
    bad.write_text("default: v1\n", encoding="utf-8")
    monkeypatch.setenv(registry.CONFIG_ENV, str(bad))
    registry.reload()
    with pytest.raises(ModelUnavailableError, match="missing keys"):
        interface.predict("x = 1", "python")


def test_environment_variables_choose_the_config(tmp_path, monkeypatch):
    cfg = write_config(
        tmp_path, [{**V1, "kind": "stub", "version": "v7"}], default="v7", fallback="v7"
    )
    monkeypatch.setenv(registry.CONFIG_ENV, str(cfg))
    monkeypatch.setenv(registry.ARTIFACT_ENV, str(tmp_path / "files"))
    registry.reload()
    reg = registry.default_registry()
    assert reg.config.default == "v7"
    assert reg.artifact_dir == tmp_path / "files"
