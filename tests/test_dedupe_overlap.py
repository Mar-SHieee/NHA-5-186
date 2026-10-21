"""No normalized code hash is shared by two deduped datasets."""

from __future__ import annotations

import itertools
import os
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from languages import registry
from shield_core.datasets.dedupe import ConservativeNormalizer, Sha256Hasher, build_normalizers

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
REQUIRE_ENV = "SHIELD_REQUIRE_DEDUPED_DATA"
SUFFIX = "_deduped.parquet"


def deduped_files() -> dict[str, Path]:
    return {p.name.removesuffix(SUFFIX): p for p in sorted(INTERIM.glob(f"*{SUFFIX}"))}


def code_hash(
    code: object,
    language: object,
    normalizers: dict,
    fallback: ConservativeNormalizer,
    hasher: Sha256Hasher,
) -> str:
    if not isinstance(code, str):
        return ""
    lang = str(language)
    normalized = normalizers.get(lang, fallback).normalize(code)
    return hasher.hash(lang + "\0" + normalized) if normalized else ""


def normalized_hashes(path: Path) -> set[str]:
    normalizers = build_normalizers(registry.all_languages())
    fallback = ConservativeNormalizer()
    hasher = Sha256Hasher()
    hashes: set[str] = set()
    for batch in pq.ParquetFile(path).iter_batches(batch_size=1_000, columns=["code", "language"]):
        codes = batch.column("code").to_pylist()
        languages = batch.column("language").to_pylist()
        for code, language in zip(codes, languages, strict=True):
            value = code_hash(code, language, normalizers, fallback, hasher)
            if value:
                hashes.add(value)
    return hashes


@pytest.fixture(scope="module")
def hash_sets() -> dict[str, set[str]]:
    files = deduped_files()
    if len(files) < 2:
        message = f"fewer than two deduped datasets in {INTERIM}"
        if os.getenv(REQUIRE_ENV) == "1":
            pytest.fail(message)
        pytest.skip(message)
    return {name: normalized_hashes(path) for name, path in files.items()}


def test_deduped_datasets_exist() -> None:
    if not deduped_files() and os.getenv(REQUIRE_ENV) != "1":
        pytest.skip(f"no deduped datasets in {INTERIM}; set {REQUIRE_ENV}=1 to require them")
    assert deduped_files(), f"no deduped datasets in {INTERIM}"


def test_no_normalized_overlap_between_datasets(hash_sets: dict[str, set[str]]) -> None:
    pairs = itertools.combinations(hash_sets, 2)
    shared = {(a, b): len(hash_sets[a] & hash_sets[b]) for a, b in pairs}
    shared = {pair: count for pair, count in shared.items() if count}
    assert not shared, f"shared normalized hashes between datasets: {shared}"
