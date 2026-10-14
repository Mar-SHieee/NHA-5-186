from __future__ import annotations

import hashlib
import importlib
import os
import random
from pathlib import Path
from typing import Any

BACKEND_ENV = "SHIELD_TRACKER"
DEFAULT_PROJECT = "shield"
CHUNK_SIZE = 1024 * 1024  # read big files 1 MB at a time

_RESERVED_KEYS = ("seed", "dataset_hash")
_SCALARS = (str, int, float, bool)


# ------------------------------ seed ---------------------------------------------


def _optional(name: str) -> Any:
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def set_seed(seed: int) -> None:
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)  # only affects processes started after this
    numpy = _optional("numpy")
    if numpy is not None:
        numpy.random.seed(seed)
    torch = _optional("torch")
    if torch is not None:
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)


# ------------------------- hashing --------------------------------------------------


def hash_file(path: Path | str, chunk_size: int = CHUNK_SIZE) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def hash_dataset(path: Path | str, chunk_size: int = CHUNK_SIZE) -> str:
    path = Path(path)
    if path.is_file():
        return f"sha256:{hash_file(path, chunk_size)}"
    if path.is_dir():
        digest = hashlib.sha256()
        files = sorted((p for p in path.rglob("*") if p.is_file()), key=lambda p: p.as_posix())
        for file in files:
            digest.update(file.relative_to(path).as_posix().encode("utf-8") + b"\0")
            digest.update(hash_file(file, chunk_size).encode("ascii") + b"\0")
        return f"sha256:{digest.hexdigest()}"
    raise FileNotFoundError(f"dataset path not found: {path}")


# --------------------------------- config ------------------------------------------


def _flatten(config: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in config.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{name}."))
        elif value is None or isinstance(value, _SCALARS):
            flat[name] = value
        else:
            flat[name] = str(value)
    return flat


# -------------------------------- backends -------------------------------------------


def _require(name: str) -> Any:
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise ImportError(f"this tracker needs the '{name}' package: pip install {name}") from exc


class _ConsoleBackend:
    name = "console"
    url = None

    def __init__(self, project: str, run_name: str | None) -> None:
        print(f"[run] project={project} name={run_name}")

    def log_params(self, params: dict[str, Any]) -> None:
        print("[run] params:")
        for key in sorted(params):
            print(f"  {key} = {params[key]}")

    def log_metrics(self, metrics: dict[str, float], step: int | None) -> None:
        print(f"[run] step={step} {metrics}")

    def finish(self) -> None:
        print("[run] finished")


class _MlflowBackend:
    name = "mlflow"
    url = None

    def __init__(self, project: str, run_name: str | None) -> None:
        self._mlflow = _require("mlflow")
        self._mlflow.set_experiment(project)
        self._mlflow.start_run(run_name=run_name)

    def log_params(self, params: dict[str, Any]) -> None:
        self._mlflow.log_params(params)

    def log_metrics(self, metrics: dict[str, float], step: int | None) -> None:
        self._mlflow.log_metrics(metrics, step=step)

    def finish(self) -> None:
        self._mlflow.end_run()


class _WandbBackend:
    name = "wandb"

    def __init__(self, project: str, run_name: str | None) -> None:
        self._wandb = _require("wandb")
        self._run = self._wandb.init(project=project, name=run_name)
        self.url = getattr(self._run, "url", None)

    def log_params(self, params: dict[str, Any]) -> None:
        self._run.config.update(params)

    def log_metrics(self, metrics: dict[str, float], step: int | None) -> None:
        self._run.log(metrics, step=step)

    def finish(self) -> None:
        self._run.finish()


BACKENDS = {
    "console": _ConsoleBackend,
    "mlflow": _MlflowBackend,
    "wandb": _WandbBackend,
}


# ---------------------------------- the run -----------------------------------------


class RunLogger:
    """One tracked run. Use it as a context manager so it always closes."""

    def __init__(self, backend: Any, params: dict[str, Any]) -> None:
        self._backend = backend
        self._finished = False
        self.params = params
        try:
            backend.log_params(params)
        except Exception:
            backend.finish()
            raise

    @property
    def backend_name(self) -> str:
        return self._backend.name

    @property
    def url(self) -> str | None:
        return self._backend.url

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        self._backend.log_metrics(metrics, step)

    def finish(self) -> None:
        if not self._finished:
            self._finished = True
            self._backend.finish()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.finish()


def start_run(
    config: dict[str, Any],
    seed: int,
    dataset_path: Path | str | None = None,
    dataset_hash: str | None = None,
    *,
    backend: str | None = None,
    project: str = DEFAULT_PROJECT,
    run_name: str | None = None,
) -> RunLogger:
    """Seed everything, fingerprint the dataset, and log config + seed + dataset hash.

    Give exactly one of dataset_path (the file or folder is hashed) or dataset_hash
    (a hash you already have, so nothing is read). Use dataset_hash="none" for a run
    that uses no dataset.
    """
    if (dataset_path is None) == (dataset_hash is None):
        raise ValueError("give exactly one of dataset_path or dataset_hash")
    clash = [key for key in _RESERVED_KEYS if key in config]
    if clash:
        raise ValueError(f"config must not use the reserved keys: {', '.join(clash)}")
    backend_name = backend or os.environ.get(BACKEND_ENV, "console")
    if backend_name not in BACKENDS:
        raise ValueError(f"unknown backend {backend_name!r}; choose one of: {', '.join(BACKENDS)}")

    set_seed(seed)
    fingerprint = hash_dataset(dataset_path) if dataset_path is not None else dataset_hash
    params = {**_flatten(config), "seed": seed, "dataset_hash": fingerprint}
    return RunLogger(BACKENDS[backend_name](project, run_name), params)
