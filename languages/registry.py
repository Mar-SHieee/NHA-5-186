"""Language registry (W1-P4-05): the single source of truth for supported languages.

Each language is described by one YAML file in this folder (python.yaml, cpp.yaml, ...).
Other code never hardcodes language names. It asks this module instead:

    from languages import registry

    registry.enabled_languages()          # ['cpp', 'python']
    registry.language_for_path("x.py")    # the LanguageSpec of python
    registry.require_enabled("java")      # raises DisabledLanguageError

Adding a language, or switching one on or off, means editing a YAML file, not code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

LANGUAGES_DIR = Path(__file__).resolve().parent

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_CWE_RE = re.compile(r"^CWE-\d+$")
_REQUIRED_KEYS = (
    "name",
    "enabled",
    "extensions",
    "joern_frontend",
    "tree_sitter",
    "cwes",
    "sources",
    "sinks",
)


# --------------------------------------------------------------------------- errors


class RegistryError(Exception):
    """Base class for every registry error."""


class LanguageConfigError(RegistryError):
    """A YAML file is missing, malformed, or breaks a rule."""


class UnknownLanguageError(RegistryError):
    """The language does not exist in the registry at all."""

    def __init__(self, name: str, known: list[str]) -> None:
        self.name = name
        self.known = tuple(known)
        super().__init__(f"unknown language: {name!r}. Known languages: {', '.join(known)}")


class DisabledLanguageError(RegistryError):
    """The language exists but is switched off."""

    def __init__(self, name: str, enabled: list[str]) -> None:
        self.name = name
        self.enabled = tuple(enabled)
        super().__init__(f"language {name!r} is disabled. Enabled languages: {', '.join(enabled)}")


# --------------------------------------------------------------------------- data


# this handle by extension which is in .c
@dataclass(frozen=True)
class TreeSitterSpec:
    default: str
    by_extension: dict[str, str] = field(default_factory=dict)

    def module_for(self, extension: str | None = None) -> str:
        """Name of the tree-sitter grammar module for a file extension (or the default)."""
        if extension is not None:
            return self.by_extension.get(extension.lower(), self.default)
        return self.default


@dataclass(frozen=True)
class LanguageSpec:
    name: str
    enabled: bool
    extensions: tuple[str, ...]
    joern_frontend: str
    tree_sitter: TreeSitterSpec
    cwes: tuple[str, ...]
    sources: tuple[str, ...]
    sinks: tuple[str, ...]


# --------------------------------------------------------------------------- parsing


def _fail(path: Path, message: str) -> LanguageConfigError:
    return LanguageConfigError(f"{path.name}: {message}")


def _string_list(
    path: Path, data: dict[str, Any], key: str, pattern: re.Pattern[str] | None = None
) -> tuple[str, ...]:
    value = data[key]
    if value is None:
        raise _fail(path, f"'{key}' is empty; write '{key}: []' for an empty list")
    if not isinstance(value, list):
        raise _fail(path, f"'{key}' must be a list")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise _fail(path, f"'{key}' must contain non-empty strings, got {item!r}")
        if pattern is not None and not pattern.match(item):
            raise _fail(path, f"'{key}' has an invalid entry {item!r} (expected like 'CWE-787')")
    return tuple(value)


def _parse_extensions(path: Path, value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise _fail(path, "'extensions' must be a non-empty list")
    for ext in value:
        if (
            not isinstance(ext, str)
            or len(ext) < 2
            or not ext.startswith(".")
            or ext != ext.lower()
        ):
            raise _fail(path, f"extension {ext!r} must be lowercase and start with a dot")
    if len(set(value)) != len(value):
        raise _fail(path, "'extensions' contains duplicates")
    return tuple(value)


def _parse_tree_sitter(path: Path, value: Any, extensions: tuple[str, ...]) -> TreeSitterSpec:
    if not isinstance(value, dict):
        raise _fail(path, "'tree_sitter' must be a mapping with a 'default' key")
    extra = sorted(str(k) for k in set(value) - {"default", "by_extension"})
    if extra:
        raise _fail(path, f"unknown keys in 'tree_sitter': {', '.join(extra)}")
    default = value.get("default")
    if not isinstance(default, str) or not default.strip():
        raise _fail(path, "'tree_sitter.default' must be a non-empty string")
    by_extension = value.get("by_extension") or {}
    if not isinstance(by_extension, dict):
        raise _fail(path, "'tree_sitter.by_extension' must be a mapping")
    for ext, module in by_extension.items():
        if ext not in extensions:
            raise _fail(
                path,
                f"'tree_sitter.by_extension' uses {ext!r}, which is not in 'extensions'",
            )
        if not isinstance(module, str) or not module.strip():
            raise _fail(path, f"'tree_sitter.by_extension' entry {ext!r} must be a string")
    return TreeSitterSpec(default=default, by_extension=dict(by_extension))


def _parse_spec(path: Path, data: Any) -> LanguageSpec:
    if not isinstance(data, dict):
        raise _fail(path, "the file must contain a mapping of keys to values")

    missing = [key for key in _REQUIRED_KEYS if key not in data]
    if missing:
        raise _fail(path, f"missing keys: {', '.join(missing)}")
    unknown = sorted(str(key) for key in set(data) - set(_REQUIRED_KEYS))
    if unknown:
        raise _fail(path, f"unknown keys: {', '.join(unknown)}")

    name = data["name"]
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise _fail(
            path,
            "'name' must be lowercase letters, digits or underscores, starting with a letter",
        )
    if name != path.stem:
        raise _fail(path, f"'name' ({name}) must match the file name ({path.stem})")

    enabled = data["enabled"]
    if not isinstance(enabled, bool):
        raise _fail(path, "'enabled' must be true or false (not a quoted string)")

    extensions = _parse_extensions(path, data["extensions"])

    joern_frontend = data["joern_frontend"]
    if not isinstance(joern_frontend, str) or not joern_frontend.strip():
        raise _fail(path, "'joern_frontend' must be a non-empty string")

    return LanguageSpec(
        name=name,
        enabled=enabled,
        extensions=extensions,
        joern_frontend=joern_frontend,
        tree_sitter=_parse_tree_sitter(path, data["tree_sitter"], extensions),
        cwes=_string_list(path, data, "cwes", _CWE_RE),
        sources=_string_list(path, data, "sources"),
        sinks=_string_list(path, data, "sinks"),
    )


def load_registry(directory: Path | str | None = None) -> dict[str, LanguageSpec]:
    """Read and validate every *.yaml file in a folder. Returns {name: spec}.

    The default folder is this package's folder. Tests pass their own folder.
    """
    folder = Path(directory) if directory is not None else LANGUAGES_DIR
    files = sorted(folder.glob("*.yaml"))
    if not files:
        raise LanguageConfigError(f"no *.yaml language files found in {folder}")

    specs: dict[str, LanguageSpec] = {}
    owner_of_extension: dict[str, str] = {}
    for path in files:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise _fail(path, f"invalid YAML ({exc})") from exc
        spec = _parse_spec(path, data)
        for ext in spec.extensions:
            if ext in owner_of_extension:
                raise _fail(
                    path,
                    f"extension {ext!r} is already used by {owner_of_extension[ext]!r}",
                )
            owner_of_extension[ext] = spec.name
        specs[spec.name] = spec
    return specs


########################################
# DEALING WITH REGISTRY USING THIS API #
########################################


@lru_cache(maxsize=1)
def _default_registry() -> dict[str, LanguageSpec]:
    return load_registry()


def reload() -> None:
    # Forget the cached registry so the next call reads the YAML files again
    _default_registry.cache_clear()


def all_languages() -> list[LanguageSpec]:
    specs = _default_registry()
    return [specs[name] for name in sorted(specs)]


def enabled_languages() -> list[str]:
    return [spec.name for spec in all_languages() if spec.enabled]


def get(name: str) -> LanguageSpec:
    specs = _default_registry()
    try:
        return specs[name]
    except KeyError:
        raise UnknownLanguageError(name, sorted(specs)) from None


def is_enabled(name: str) -> bool:
    spec = _default_registry().get(name)
    return spec is not None and spec.enabled


def require_enabled(name: str) -> LanguageSpec:
    spec = get(name)
    if not spec.enabled:
        raise DisabledLanguageError(name, enabled_languages())
    return spec


def language_for_extension(extension: str) -> LanguageSpec | None:
    ext = extension.lower()
    for spec in all_languages():
        if ext in spec.extensions:
            return spec
    return None


def language_for_path(path: Path | str) -> LanguageSpec | None:
    return language_for_extension(Path(path).suffix)
