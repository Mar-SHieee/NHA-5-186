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
    "sanitizers",
)
# Source kinds the taint code understands (W1-P2-03, docs/taint_spike.md):
#   call      the call RETURNS the tainted value              getenv("X"), input()
#   argument  the call WRITES the tainted value into one of   fgets(buf, n, stdin), read(fd, buf, n)
#             its arguments; nothing useful is returned
#   parameter a function parameter holds the tainted value    main(int argc, char **argv)
_SOURCE_KINDS = ("call", "argument", "parameter")


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
class SourceSpec:
    """Where tainted data enters. Patterns are Joern regexes: they must match the WHOLE text."""

    kind: str
    name: str | None = None  # regex on the call name (kind: parameter -> on the parameter name)
    code: str | None = None  # regex on the call's source text (kinds: call, argument)
    arg: int | None = None  # kind: argument only. Joern index of the argument that is written


@dataclass(frozen=True)
class SinkSpec:
    """A dangerous call. The dangerous value is ONE argument (`arg`) or every argument from an
    index on (`arg_from`, for variadic calls such as sprintf(dst, fmt, ...)). Exactly one is set.

    Joern argument indices: for module-qualified Python calls such as os.system(x) index 0 is
    the module and the payload is 1; for bare calls such as open(x) or C's system(x) the payload
    is also 1. For a C++ member call index 0 is the receiver.
    """

    name: str  # regex on the call name
    arg: int | None = None
    code: str | None = None  # regex on the call's source text, to tell apart same-name calls
    cwe: str | None = None
    arg_from: int | None = None


@dataclass(frozen=True)
class LanguageSpec:
    name: str
    enabled: bool
    extensions: tuple[str, ...]
    joern_frontend: str
    tree_sitter: TreeSitterSpec
    cwes: tuple[str, ...]
    sources: tuple[SourceSpec, ...]
    sinks: tuple[SinkSpec, ...]
    # Regexes on call names. A taint path is flagged when such a call is a path element OR the
    # call a path element is an argument of (Joern lists the arguments of an output-parameter
    # sanitizer, not the call itself; see docs/taint_spike.md, c22a/c22b).
    sanitizers: tuple[str, ...]


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


def _regex(path: Path, where: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail(path, f"{where} must be a non-empty string")
    try:
        re.compile(value)
    except re.error as exc:
        raise _fail(path, f"{where} is not a valid regex ({exc})") from exc
    return value


def _entries(path: Path, data: dict[str, Any], key: str) -> list[Any]:
    value = data[key]
    if value is None:
        raise _fail(path, f"'{key}' is empty; write '{key}: []' for an empty list")
    if not isinstance(value, list):
        raise _fail(path, f"'{key}' must be a list")
    return value


def _entry_mapping(path: Path, where: str, item: Any, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise _fail(path, f"{where} must be a mapping")
    extra = sorted(str(k) for k in set(item) - allowed)
    if extra:
        raise _fail(path, f"unknown keys in {where}: {', '.join(extra)}")
    return item


def _index(path: Path, where: str, key: str, value: Any, minimum: int) -> int:
    # bool is a subclass of int in Python, so exclude it explicitly
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _fail(path, f"{where} '{key}' must be an integer >= {minimum}")
    return value


def _parse_sources(path: Path, data: dict[str, Any]) -> tuple[SourceSpec, ...]:
    result = []
    for i, raw in enumerate(_entries(path, data, "sources")):
        where = f"'sources[{i}]'"
        item = _entry_mapping(path, where, raw, {"kind", "name", "code", "arg"})
        kind = item.get("kind")
        if kind not in _SOURCE_KINDS:
            raise _fail(path, f"{where} 'kind' must be one of: {', '.join(_SOURCE_KINDS)}")
        name = _regex(path, f"{where} 'name'", item["name"]) if "name" in item else None
        code = _regex(path, f"{where} 'code'", item["code"]) if "code" in item else None
        arg = None
        if kind == "call":
            if "arg" in item:
                raise _fail(path, f"{where} 'arg' is only valid for kind 'argument'")
            if name is None and code is None:
                raise _fail(path, f"{where} needs 'name' or 'code'")
        elif kind == "argument":
            if name is None:
                raise _fail(path, f"{where} of kind 'argument' needs 'name' (the call)")
            if "arg" not in item:
                raise _fail(path, f"{where} of kind 'argument' needs 'arg'")
            arg = _index(path, where, "arg", item["arg"], 0)
        else:  # parameter
            if name is None:
                raise _fail(path, f"{where} of kind 'parameter' needs 'name' (the parameter)")
            if code is not None or "arg" in item:
                raise _fail(path, f"{where} of kind 'parameter' takes only 'name'")
        result.append(SourceSpec(kind=kind, name=name, code=code, arg=arg))
    return tuple(result)


def _parse_sinks(path: Path, data: dict[str, Any]) -> tuple[SinkSpec, ...]:
    result = []
    for i, raw in enumerate(_entries(path, data, "sinks")):
        where = f"'sinks[{i}]'"
        item = _entry_mapping(path, where, raw, {"name", "arg", "arg_from", "code", "cwe"})
        if "name" not in item:
            raise _fail(path, f"{where} is missing: name")
        name = _regex(path, f"{where} 'name'", item["name"])
        has_arg, has_from = "arg" in item, "arg_from" in item
        if has_arg and has_from:
            raise _fail(path, f"{where} cannot have both 'arg' and 'arg_from'")
        if not has_arg and not has_from:
            raise _fail(path, f"{where} needs one of 'arg' or 'arg_from'")
        arg = _index(path, where, "arg", item["arg"], 0) if has_arg else None
        arg_from = _index(path, where, "arg_from", item["arg_from"], 1) if has_from else None
        code = _regex(path, f"{where} 'code'", item["code"]) if "code" in item else None
        cwe = item.get("cwe")
        if cwe is not None and (not isinstance(cwe, str) or not _CWE_RE.match(cwe)):
            raise _fail(path, f"{where} has an invalid 'cwe' {cwe!r} (expected like 'CWE-89')")
        result.append(SinkSpec(name=name, arg=arg, code=code, cwe=cwe, arg_from=arg_from))
    return tuple(result)


def _parse_sanitizers(path: Path, data: dict[str, Any]) -> tuple[str, ...]:
    names = _string_list(path, data, "sanitizers")
    for name in names:
        _regex(path, f"'sanitizers' entry {name!r}", name)
    return names


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
        sources=_parse_sources(path, data),
        sinks=_parse_sinks(path, data),
        sanitizers=_parse_sanitizers(path, data),
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
