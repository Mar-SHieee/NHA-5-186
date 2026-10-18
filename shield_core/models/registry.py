"""Model registry (W2-P4-02): the catalog of trained models.

predict() asks this module for a model and never touches model files itself, so a new
model version is a config change, not a code change.

    from shield_core.models import registry

    model = registry.get_model("python")      # the default model, or the V1 fallback
    model.version                             # which model answered
    registry.get_model("python", "v2")        # a specific version, no fallback

How a model is chosen when no version is given:
  1. the default version, if its entry lists the language;
  2. otherwise, or if it cannot be loaded, the fallback version (logged as a warning);
  3. if no entry lists the language, the built-in stub (model_version "stub");
  4. if entries exist but none can be loaded, ModelLoadError. Never a silent stub.

Not to be confused with languages/registry.py, which is the catalog of languages.
"""

from __future__ import annotations

import importlib
import logging
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Protocol

import yaml

from languages import registry as language_registry
from shield_core.tracking import hash_file

if TYPE_CHECKING:
    from shield_core.interface import Result

log = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = MODELS_DIR / "models.yaml"
DEFAULT_ARTIFACT_DIR = MODELS_DIR.parents[1] / "model_artifacts"
CONFIG_ENV = "SHIELD_MODELS_CONFIG"
ARTIFACT_ENV = "SHIELD_MODELS_DIR"

STUB_VERSION = "stub"

_VERSION_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOP_KEYS = ("default", "fallback", "models")
_ENTRY_REQUIRED = ("version", "kind", "languages")
_ENTRY_OPTIONAL = ("path", "sha256", "options")


# ---------------------- errors -------------------------------------


class ModelRegistryError(Exception):
    """Base class"""


class ModelConfigError(ModelRegistryError):
    """The config file is missing"""


class UnknownModelVersionError(ModelRegistryError):
    """A specific version was requested that does not exist or does not support the language"""


class ModelLoadError(ModelRegistryError):
    """A model exists in the config but could not be loaded"""


# ---------------------------------- models -----------------------------------------


class Model(Protocol):
    """What the registry hands out. predict() asks it for a Result."""

    version: str

    def predict(self, code: str, language: str) -> Result: ...


class StubModel:
    """Placeholder: always says 'not vulnerable'. Used until the real V1 is swapped in"""

    version = STUB_VERSION

    def predict(self, code: str, language: str) -> Result:
        from shield_core.interface import Result

        return Result(
            vulnerable=False,
            cwe=None,
            confidence=0.0,
            model_version=self.version,
        )


# -------------------------------- config -------------------------------------------


@dataclass(frozen=True)
class ModelEntry:
    version: str
    kind: str
    languages: tuple[str, ...]
    path: str | None = None
    sha256: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RegistryConfig:
    default: str
    fallback: str
    models: dict[str, ModelEntry]


def _fail(path: Path, message: str) -> ModelConfigError:
    return ModelConfigError(f"{path.name}: {message}")


def _safe_relative_path(value: str) -> bool:
    parts = value.replace("\\", "/").split("/")
    return (
        bool(value) and not value.startswith(("/", "\\")) and ":" not in value and ".." not in parts
    )


def _parse_entry(path: Path, raw: Any, index: int, known: set[str]) -> ModelEntry:
    where = f"models[{index}]"
    if not isinstance(raw, dict):
        raise _fail(path, f"{where} must be a mapping")
    missing = [key for key in _ENTRY_REQUIRED if key not in raw]
    if missing:
        raise _fail(path, f"{where}: missing keys: {', '.join(missing)}")
    unknown = sorted(str(key) for key in set(raw) - set(_ENTRY_REQUIRED) - set(_ENTRY_OPTIONAL))
    if unknown:
        raise _fail(path, f"{where}: unknown keys: {', '.join(unknown)}")

    version = raw["version"]
    if not isinstance(version, str) or not _VERSION_RE.match(version):
        raise _fail(path, f"{where}: 'version' must be lowercase letters, digits, '.', '_' or '-'")
    if version == STUB_VERSION:
        raise _fail(path, f"{where}: version {STUB_VERSION!r} is reserved for the built-in stub")

    kind = raw["kind"]
    if not isinstance(kind, str) or not kind.strip():
        raise _fail(path, f"{where}: 'kind' must be a non-empty string")

    languages = raw["languages"]
    if not isinstance(languages, list) or not languages:
        raise _fail(path, f"{where}: 'languages' must be a non-empty list")
    for lang in languages:
        if lang not in known:
            raise _fail(path, f"{where}: unknown language {lang!r}")
    if len(set(languages)) != len(languages):
        raise _fail(path, f"{where}: 'languages' contains duplicates")

    file_path = raw.get("path")
    if file_path is not None and (
        not isinstance(file_path, str) or not _safe_relative_path(file_path)
    ):
        raise _fail(path, f"{where}: 'path' must be a relative path inside the model folder")

    sha256 = raw.get("sha256")
    if sha256 is not None and (not isinstance(sha256, str) or not _SHA256_RE.match(sha256)):
        raise _fail(path, f"{where}: 'sha256' must be 64 lowercase hex characters")

    options = raw.get("options") or {}
    if not isinstance(options, dict):
        raise _fail(path, f"{where}: 'options' must be a mapping")

    return ModelEntry(
        version=version,
        kind=kind,
        languages=tuple(languages),
        path=file_path,
        sha256=sha256,
        options=dict(options),
    )


def load_config(path: Path | str, known_languages: set[str] | None = None) -> RegistryConfig:
    """Read and validate a model catalog file."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ModelConfigError(f"{path.name}: cannot read the config file ({exc})") from exc
    except yaml.YAMLError as exc:
        raise _fail(path, f"invalid YAML ({exc})") from exc

    if not isinstance(data, dict):
        raise _fail(path, "the file must contain a mapping of keys to values")
    missing = [key for key in _TOP_KEYS if key not in data]
    if missing:
        raise _fail(path, f"missing keys: {', '.join(missing)}")
    unknown = sorted(str(key) for key in set(data) - set(_TOP_KEYS))
    if unknown:
        raise _fail(path, f"unknown keys: {', '.join(unknown)}")

    raw_models = data["models"]
    if not isinstance(raw_models, list) or not raw_models:
        raise _fail(path, "'models' must be a non-empty list")

    known = (
        set(known_languages)
        if known_languages is not None
        else {spec.name for spec in language_registry.all_languages()}
    )
    models: dict[str, ModelEntry] = {}
    for index, raw in enumerate(raw_models):
        entry = _parse_entry(path, raw, index, known)
        if entry.version in models:
            raise _fail(path, f"duplicate version {entry.version!r}")
        models[entry.version] = entry

    for key in ("default", "fallback"):
        value = data[key]
        if value not in models:
            raise _fail(path, f"'{key}' must name a version in 'models' (got {value!r})")

    return RegistryConfig(default=data["default"], fallback=data["fallback"], models=models)


# ----------------------------------- loaders ----------------------------------------

Loader = Callable[[ModelEntry, Path], Model]


def _load_stub(entry: ModelEntry, artifact_dir: Path) -> Model:
    return StubModel()


# A kind maps to a loader function, or to "package.module:function", which is imported only
# when a model of that kind is loaded, so heavy libraries (xgboost, torch) are not imported
# at startup. Day 5: add one line here for the real V1, for example
#     "xgboost_codebert": "shield_core.models.v1:load",
KINDS: dict[str, Loader | str] = {"stub": _load_stub}


def register_kind(kind: str, loader: Loader | str) -> None:
    """Add or replace a model kind. Call it before the first get_model()."""
    KINDS[kind] = loader


def _resolve_loader(target: Loader | str | None, entry: ModelEntry) -> Loader:
    if target is None:
        raise ModelLoadError(f"model {entry.version}: unknown kind {entry.kind!r}")
    if callable(target):
        return target
    module_name, _, function_name = target.partition(":")
    try:
        return getattr(importlib.import_module(module_name), function_name)
    except (ImportError, AttributeError) as exc:
        raise ModelLoadError(
            f"model {entry.version}: cannot import the loader for kind {entry.kind!r} ({exc})"
        ) from exc


# ---------------------------------- the registry -----------------------------------------


class ModelRegistry:
    """The catalog: reads the config once, loads models on demand, remembers the result."""

    def __init__(
        self,
        config_path: Path | str = DEFAULT_CONFIG,
        artifact_dir: Path | str = DEFAULT_ARTIFACT_DIR,
        kinds: dict[str, Loader | str] | None = None,
    ) -> None:
        self.config = load_config(config_path)
        self.artifact_dir = Path(artifact_dir)
        self._kinds = {**KINDS, **(kinds or {})}
        self._loaded: dict[str, Model] = {}
        self._failed: dict[str, ModelLoadError] = {}

    def get_model(self, language: str, version: str | None = None) -> Model:
        """The model that answers for a language. See the module docstring for the rules."""
        if version is not None:
            return self._load(self._entry_for(version, language))

        candidates: list[ModelEntry] = []
        for name in (self.config.default, self.config.fallback):
            entry = self.config.models[name]
            if language in entry.languages and entry not in candidates:
                candidates.append(entry)
        if not candidates:
            return StubModel()

        problems: list[str] = []
        for position, entry in enumerate(candidates):
            try:
                model = self._load(entry)
            except ModelLoadError as exc:
                log.warning("%s", exc)
                problems.append(str(exc))
                continue
            if position > 0:
                log.warning(
                    "model %s is not available for %s, using %s instead",
                    candidates[0].version,
                    language,
                    entry.version,
                )
            return model
        raise ModelLoadError(
            f"no model could be loaded for language {language!r}: " + "; ".join(problems)
        )

    def _entry_for(self, version: str, language: str) -> ModelEntry:
        entry = self.config.models.get(version)
        if entry is None:
            known = ", ".join(self.config.models)
            raise UnknownModelVersionError(f"unknown model version {version!r}. Known: {known}")
        if language not in entry.languages:
            raise UnknownModelVersionError(
                f"model {version} does not support language {language!r}"
            )
        return entry

    def _load(self, entry: ModelEntry) -> Model:
        if entry.version in self._loaded:
            return self._loaded[entry.version]
        if entry.version in self._failed:
            raise self._failed[entry.version]
        try:
            model = self._build(entry)
        except ModelLoadError as exc:
            self._failed[entry.version] = exc
            raise
        self._loaded[entry.version] = model
        return model

    def _build(self, entry: ModelEntry) -> Model:
        if entry.path is not None:
            file = self.artifact_dir / entry.path
            if not file.exists():
                raise ModelLoadError(f"model {entry.version}: file not found: {file}")
            if entry.sha256 is not None:
                if not file.is_file():
                    raise ModelLoadError(f"model {entry.version}: 'sha256' needs a file: {file}")
                if hash_file(file) != entry.sha256:
                    raise ModelLoadError(
                        f"model {entry.version}: checksum mismatch for {file.name} "
                        "(the file is corrupt or not the expected version)"
                    )
        loader = _resolve_loader(self._kinds.get(entry.kind), entry)
        try:
            return loader(entry, self.artifact_dir)
        except ModelLoadError:
            raise
        except Exception as exc:  # a corrupt file can make any library raise anything
            raise ModelLoadError(
                f"model {entry.version} ({entry.kind}) failed to load: {exc}"
            ) from exc


# ---------------------------- module API -----------------------------------------------


@lru_cache(maxsize=1)
def default_registry() -> ModelRegistry:
    """The registry predict() uses. Paths come from SHIELD_MODELS_CONFIG and SHIELD_MODELS_DIR."""
    config = Path(os.environ.get(CONFIG_ENV) or DEFAULT_CONFIG)
    artifacts = Path(os.environ.get(ARTIFACT_ENV) or DEFAULT_ARTIFACT_DIR)
    return ModelRegistry(config, artifacts)


def get_model(language: str, version: str | None = None) -> Model:
    return default_registry().get_model(language, version)


def reload() -> None:
    """Forget the config and every loaded model. The next get_model() starts fresh."""
    default_registry.cache_clear()
