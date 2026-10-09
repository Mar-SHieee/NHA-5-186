import os

import pandas as pd

from scripts.long_function_analysis import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_STRIDE,
    apply_truncation_policy,
    count_tokens,
)
from shield_core.models.embedding.embedder import CodeBERTEmbedder

DATA_PATH = "data/interim/megavul.parquet"
OUTPUT_PATH = "data/interim/megavul_processed.parquet"
CACHE_DIR = "data/cache"

BATCH_SIZE = 16


def process_dataset(df, embedder, batch_size=BATCH_SIZE):
    if "code" not in df.columns:
        raise ValueError("Dataset must contain a 'code' column.")

    if batch_size <= 0:
        raise ValueError("batch_size must be positive.")

    df = df.copy()

    print("1. Calculating token lengths...")

    df["token_count"] = df["code"].apply(count_tokens)

    print("2. Applying Sliding Window...")

    results = df["code"].apply(
        lambda code: apply_truncation_policy(
            code,
            max_tokens=DEFAULT_MAX_TOKENS,
            stride=DEFAULT_STRIDE,
        )
    )

    df["processed_code"] = results.apply(lambda result: result[0])
    df["was_truncated"] = results.apply(lambda result: result[1])
    df["num_chunks"] = df["processed_code"].apply(len)

    print(f"Total functions: {len(df)}")
    print(
        f"Functions over {DEFAULT_MAX_TOKENS} tokens: "
        f"{(df['token_count'] > DEFAULT_MAX_TOKENS).sum()}"
    )
    print(f"Functions split into chunks: {df['was_truncated'].sum()}")
    print(f"Total chunks: {df['num_chunks'].sum()}")

    print("3. Generating CodeBERT embeddings in batches...")

    all_chunks = []
    chunk_counts = []

    for chunks in df["processed_code"]:
        chunk_counts.append(len(chunks))
        all_chunks.extend(chunks)

    all_embeddings = []

    for start in range(0, len(all_chunks), batch_size):
        batch = all_chunks[start : start + batch_size]

        embeddings = embedder.get_embeddings_batch(
            batch,
            batch_size=batch_size,
        )

        all_embeddings.extend(
            embedding.tolist() if embedding is not None else None for embedding in embeddings
        )

    offset = 0
    grouped_embeddings = []

    for count in chunk_counts:
        grouped_embeddings.append(all_embeddings[offset : offset + count])
        offset += count

    df["embeddings"] = grouped_embeddings

    print("4. Pipeline completed.")

    return df


if __name__ == "__main__":
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Dataset not found: {DATA_PATH}")

    print(f"Loading dataset from {DATA_PATH}...")

    df = pd.read_parquet(DATA_PATH)

    embedder = CodeBERTEmbedder(
        cache_dir=CACHE_DIR,
        max_tokens=DEFAULT_MAX_TOKENS,
    )

    processed_df = process_dataset(
        df,
        embedder,
        batch_size=BATCH_SIZE,
    )

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    processed_df.to_parquet(OUTPUT_PATH, index=False)

    print(f"Processed dataset saved to {OUTPUT_PATH}")
