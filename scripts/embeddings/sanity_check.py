from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent  # SHIELD/
DATA = ROOT / "data" / "interim"

m = np.load(DATA / "megavul_deduped_embeddings.npy")
d = pd.read_parquet(DATA / "megavul_deduped_processed.parquet")

print("shape:", m.shape, "| NaNs:", int(np.isnan(m).sum()))
print("rows with embedding:", d["has_embedding"].mean())
print("all-zero rows:", int((np.abs(m).sum(axis=1) == 0).sum()))
print(d["num_chunks"].describe())
