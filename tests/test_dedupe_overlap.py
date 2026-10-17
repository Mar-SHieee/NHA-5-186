"""Tests and utilities for overlap between deduped datasets."""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq

from languages import registry
from shield_core.datasets.dedupe import (
    ConservativeNormalizer,
    Sha256Hasher,
    build_normalizers,
)

ROOT = Path(__file__).resolve().parents[1]

DATASETS = {
    "MegaVul": ROOT / "data" / "interim" / "megavul_deduped.parquet",
    "Big-Vul": ROOT / "data" / "interim" / "bigvul_deduped.parquet",
}


def get_hash(
    code: object,
    language: str,
    normalizers: dict,
    fallback: ConservativeNormalizer,
    hasher: Sha256Hasher,
) -> str:
    """Normalize code using the project's existing rules and return its hash."""
    if not isinstance(code, str):
        return ""

    normalizer = normalizers.get(language, fallback)
    normalized = normalizer.normalize(code)

    return hasher.hash(normalized) if normalized else ""


def normalized_hashes(path: Path) -> set[str]:
    """Return normalized code hashes using memory-efficient batch reading."""
    normalizers = build_normalizers(registry.all_languages())
    fallback = ConservativeNormalizer()
    hasher = Sha256Hasher()

    hashes: set[str] = set()
    parquet_file = pq.ParquetFile(path)

    for batch in parquet_file.iter_batches(
        batch_size=1_000,
        columns=["code", "language"],
    ):
        codes = batch.column("code").to_pylist()
        languages = batch.column("language").to_pylist()

        for code, language in zip(codes, languages, strict=True):
            value = get_hash(
                code,
                language,
                normalizers,
                fallback,
                hasher,
            )
            if value:
                hashes.add(value)

    return hashes


def test_deduped_datasets_exist() -> None:
    """Ensure both deduplicated datasets are available."""
    for path in DATASETS.values():
        assert path.is_file(), f"Missing deduplicated dataset: {path}"


def test_normalized_overlap_between_megavul_and_bigvul() -> None:
    """Report the number of normalized code hashes shared by both datasets."""
    missing = [str(path) for path in DATASETS.values() if not path.is_file()]
    if missing:
        import pytest

        pytest.skip(f"Deduplicated datasets are missing: {missing}")

    hash_sets = {name: normalized_hashes(path) for name, path in DATASETS.items()}

    shared = hash_sets["MegaVul"] & hash_sets["Big-Vul"]

    print(f"MegaVul unique normalized hashes: {len(hash_sets['MegaVul']):,}")
    print(f"Big-Vul unique normalized hashes: {len(hash_sets['Big-Vul']):,}")
    print(f"Shared normalized hashes: {len(shared):,}")

    assert not shared, (
        f"Found {len(shared):,} shared normalized hashes between MegaVul and Big-Vul."
    )
