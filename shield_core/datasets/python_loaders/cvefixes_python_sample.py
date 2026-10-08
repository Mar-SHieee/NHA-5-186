"""Random sample of the CVEfixes (Python) parquet, for the Joern spike (W1-P1-02).

Reads ``data/interim/cvefixes_python.parquet`` and writes
``data/interim/cvefixes_python_samples_20.parquet`` (seeded, so the same rows
come out on every run and every machine).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# <this file> -> python_loaders -> datasets -> shield_core -> project root
REPO_ROOT = Path(__file__).resolve().parents[3]


class CVEfixesPythonSampler:
    """Draws a seeded random sample from the unified CVEfixes (Python) table."""

    NAME = "cvefixes_python"  # input is <NAME>.parquet, output is <NAME>_samples_<n>.parquet
    SAMPLE_SIZE = 20
    RANDOM_STATE = 42

    # How the input parquet is built. convert_db downloads CVEfixes (very large, slow),
    # so it is only named in the error message and never started from here.
    BUILD_STEPS = (
        "shield_core.datasets.python_loaders.cvefixes_python_convert_db",
        "shield_core.datasets.python_loaders.cvefixes_python_tables_extraction",
        "shield_core.datasets.python_loaders.cvefixes_python_loaders",
    )

    # ---------- setup ----------

    def __init__(
        self,
        data_dir: Path | None = None,
        sample_size: int | None = None,
        random_state: int | None = None,
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir else REPO_ROOT / "data" / "interim"
        self.sample_size = sample_size if sample_size is not None else self.SAMPLE_SIZE
        self.random_state = random_state if random_state is not None else self.RANDOM_STATE

    # ---------- steps ----------

    def _input_path(self) -> Path:
        """Where the unified parquet lives."""
        return self.data_dir / f"{self.NAME}.parquet"

    def _missing_dataset_message(self, path: Path) -> str:
        """Error text that lists, in order, how to build the missing parquet."""
        steps = "\n".join(f"  {i}. python -m {step}" for i, step in enumerate(self.BUILD_STEPS, 1))
        return (
            f"Dataset not found: {path}\n"
            f"Build it from the project root, in this order "
            f"(skip the steps you already did):\n{steps}"
        )

    def _load_dataset(self) -> pd.DataFrame:
        """Read the unified parquet, with a clear error if it is missing."""
        path = self._input_path()
        if not path.exists():
            raise FileNotFoundError(self._missing_dataset_message(path))
        return pd.read_parquet(path)

    def _effective_size(self, df: pd.DataFrame) -> int:
        """Sample size, capped at the number of rows."""
        return min(self.sample_size, len(df))

    def _draw_sample(self, df: pd.DataFrame) -> pd.DataFrame:
        """Seeded random rows, without replacement."""
        return df.sample(n=self._effective_size(df), random_state=self.random_state)

    def _output_path(self, sample_rows: int) -> Path:
        """Where the sample is written."""
        return self.data_dir / f"{self.NAME}_samples_{sample_rows}.parquet"

    def _save_sample(self, sample: pd.DataFrame) -> Path:
        """Write the sample to the interim folder."""
        path = self._output_path(len(sample))
        sample.to_parquet(path, index=False)
        return path

    def _display_path(self, path: Path) -> Path:
        """Path relative to the repo when possible, for readable logs."""
        try:
            return path.relative_to(REPO_ROOT)
        except ValueError:
            return path

    def _print_logs(self, df: pd.DataFrame, sample: pd.DataFrame, output_path: Path) -> None:
        """Row counts and the label split of the sample."""
        vulnerable = int((sample["label"] == 1).sum())
        print(
            f"[{self.NAME}] "
            f"dataset_rows={len(df):,} "
            f"sample_rows={len(sample):,} "
            f"vulnerable={vulnerable} "
            f"not_vulnerable={len(sample) - vulnerable} "
            f"output={self._display_path(output_path)}"
        )

    # ---------- the only method called from outside ----------

    def execute_pipeline(self) -> Path:
        """Load, sample, save, log. Returns the output path."""
        df = self._load_dataset()
        sample = self._draw_sample(df)
        output_path = self._save_sample(sample)
        self._print_logs(df, sample, output_path)
        return output_path


def main() -> None:
    """Create the sample."""
    CVEfixesPythonSampler().execute_pipeline()


if __name__ == "__main__":
    main()
