"""Create random samples from the unified datasets."""

from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data" / "interim"

DATASETS = {
    "megavul": DATA_DIR / "megavul.parquet",
    "bigvul": DATA_DIR / "bigvul.parquet",
}

SAMPLE_SIZE = 20
RANDOM_STATE = 42


def create_sample(name: str, input_path: Path) -> None:
    """Create and save a random sample from one dataset."""
    if not input_path.exists():
        raise FileNotFoundError(f"Dataset not found: {input_path}")

    df = pd.read_parquet(input_path)

    sample_size = min(SAMPLE_SIZE, len(df))

    sample = df.sample(
        n=sample_size,
        random_state=RANDOM_STATE,
    )

    output_path = DATA_DIR / f"{name}_samples_{sample_size}.parquet"
    sample.to_parquet(output_path, index=False)

    print(
        f"[{name}] "
        f"dataset_rows={len(df):,} "
        f"sample_rows={len(sample):,} "
        f"output={output_path.relative_to(REPO_ROOT)}"
    )


def main() -> None:
    """Create samples for all datasets."""
    for name, path in DATASETS.items():
        create_sample(name, path)


if __name__ == "__main__":
    main()
