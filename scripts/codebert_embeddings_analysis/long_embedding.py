"""Embed every function in a dataset, splitting long ones into sliding windows.

Run from the project root:
    ex : python -m scripts.codebert_embeddings_analysis.long_embedding \
        --data data/interim/splits/train.parquet
    python -m scripts.codebert_embeddings_analysis.long_embedding
    python -m scripts.codebert_embeddings_analysis.long_embedding --limit 200
    python -m scripts.codebert_embeddings_analysis.long_embedding \
        --data data/interim/bigvul_deduped.parquet --overlap 128 --max-windows 12

Outputs (names come from the input file's name):
    <stem>_processed.parquet   metadata only: token_count, was_truncated, num_chunks, has_embedding
    <stem>_embeddings.npy      float32 matrix, one pooled vector per function

Row i of the parquet matches row i of the matrix. Do not sort or shuffle either file alone.
Rows with has_embedding == False (empty code) hold a zero vector: filter them before training.
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from scripts.codebert_embeddings_analysis.long_function_analysis import (
    DEFAULT_MAX_TOKENS,
    apply_truncation_policy,
    count_tokens,
)
from shield_core.models.embedding.embedder import CodeBERTEmbedder

# ----------------------------------------------------------------------- settings
# Change these defaults here, or override them on the command line.

DATA_PATH = "data/interim/megavul_deduped.parquet"
OUTPUT_DIR = "data/interim"
CACHE_DIR = "data/cache"

BATCH_SIZE = 128
OVERLAP = 64
MAX_WINDOWS: int | None = None  # None = no cap
FALLBACK_DIM = 768  # used only if no chunk could be embedded


# ----------------------------------------------------------------------- pipeline


def process_dataset(
    df: pd.DataFrame,
    embedder,
    batch_size: int = BATCH_SIZE,
    overlap: int = OVERLAP,
    max_windows: int | None = MAX_WINDOWS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Return (metadata dataframe, embedding matrix), aligned row by row."""
    if "code" not in df.columns:
        raise ValueError("Dataset must contain a 'code' column.")

    if batch_size <= 0:
        raise ValueError("batch_size must be positive.")

    df = df.copy().reset_index(drop=True)

    print("1. Calculating token lengths...")
    df["token_count"] = df["code"].apply(count_tokens)

    print(f"2. Applying sliding window (overlap={overlap}, max_windows={max_windows})...")
    results = df["code"].apply(
        lambda code: apply_truncation_policy(
            code,
            max_tokens=max_tokens,
            overlap=overlap,
            max_windows=max_windows,
        )
    )
    chunk_lists = [result[0] for result in results]
    df["was_truncated"] = [result[1] for result in results]
    df["num_chunks"] = [len(chunks) for chunks in chunk_lists]

    print(f"Total functions: {len(df)}")
    print(f"Functions over {max_tokens} tokens: {(df['token_count'] > max_tokens).sum()}")
    print(f"Functions split into chunks: {df['was_truncated'].sum()}")
    print(f"Total chunks: {df['num_chunks'].sum()}")

    print("3. Generating CodeBERT embeddings...")
    all_chunks = [chunk for chunks in chunk_lists for chunk in chunks]

    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    start_time = time.perf_counter()

    all_embeddings = embedder.get_embeddings_batch(all_chunks, batch_size=batch_size)

    elapsed = time.perf_counter() - start_time
    print(f"Embedding time: {elapsed:.1f} s | {len(all_chunks) / elapsed:.1f} chunks/s")
    if torch.cuda.is_available():
        peak_gb = torch.cuda.max_memory_allocated() / 1024**3
        print(f"Peak VRAM allocated: {peak_gb:.2f} GB")

    print("4. Pooling chunk embeddings into one vector per function...")
    dim = next((e.shape[0] for e in all_embeddings if e is not None), FALLBACK_DIM)

    matrix = np.zeros((len(df), dim), dtype="float32")
    has_embedding = []
    offset = 0

    for row, count in enumerate(df["num_chunks"]):
        group = [e for e in all_embeddings[offset : offset + count] if e is not None]
        offset += count

        if group:
            matrix[row] = torch.stack(group).mean(dim=0).numpy()
            has_embedding.append(True)
        else:
            has_embedding.append(False)

    df["has_embedding"] = has_embedding

    print("5. Pipeline completed.")

    # Chunk text and per-chunk vectors are not saved: only metadata and the pooled matrix.
    return df.drop(columns=["code"], errors="ignore"), matrix


# ----------------------------------------------------------------------- command line


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data", default=DATA_PATH, help="input parquet with a 'code' column")
    parser.add_argument("--out-dir", default=OUTPUT_DIR, help="folder for the two output files")
    parser.add_argument("--cache-dir", default=CACHE_DIR)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--overlap", type=int, default=OVERLAP)
    parser.add_argument("--max-windows", type=int, default=MAX_WINDOWS)
    parser.add_argument("--no-cap", action="store_true", help="no limit on windows per function")
    parser.add_argument("--limit", type=int, default=None, help="only the first N rows (testing)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not os.path.exists(args.data):
        raise FileNotFoundError(f"Dataset not found: {args.data}")

    max_windows = None if args.no_cap else args.max_windows

    print(f"Loading dataset from {args.data}...")
    df = pd.read_parquet(args.data)
    if args.limit is not None:
        df = df.head(args.limit)

    embedder = CodeBERTEmbedder(cache_dir=args.cache_dir, max_tokens=DEFAULT_MAX_TOKENS)

    processed_df, matrix = process_dataset(
        df,
        embedder,
        batch_size=args.batch_size,
        overlap=args.overlap,
        max_windows=max_windows,
    )

    stem = Path(args.data).stem
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    parquet_path = out_dir / f"{stem}_processed.parquet"
    matrix_path = out_dir / f"{stem}_embeddings.npy"

    processed_df.to_parquet(parquet_path, index=False)
    np.save(matrix_path, matrix)

    print(f"Metadata saved to {parquet_path}")
    print(f"Embeddings saved to {matrix_path} with shape {matrix.shape}")


if __name__ == "__main__":
    main()
