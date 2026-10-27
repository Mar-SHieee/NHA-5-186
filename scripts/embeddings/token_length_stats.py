from pathlib import Path

import pandas as pd
from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parent.parent.parent  # SHIELD/
DATA = ROOT / "data" / "interim"  # change if your files are elsewhere

# name -> (filename, code column, language column or fixed language)
DATASETS = {
    "bigvul": ("bigvul.parquet", "code", "language"),
    "megavul": ("megavul.parquet", "code", "language"),
    "cvefixes_python": ("cvefixes_python.parquet", "code", "language"),
    "cvefixes_python_deduped": ("cvefixes_python_deduped.parquet", "code", "language"),
    "bigvul_deduped": ("bigvul_deduped.parquet", "code", "language"),
    "megavul_deduped": ("megavul_deduped.parquet", "code", "language"),
    "cvefixes_cpp": ("cvefixes_cpp.parquet", "code", "language"),
    "cvefixes_cpp_deduped": ("cvefixes_cpp_deduped.parquet", "code", "language"),
}

tok = AutoTokenizer.from_pretrained("microsoft/codebert-base")


def token_stats(path, code_col, lang_col):
    df = pd.read_parquet(path)
    print("columns:", list(df.columns))
    df = df[df[code_col].notna() & (df[code_col].str.strip() != "")].copy()
    ids = tok(df[code_col].tolist(), add_special_tokens=True, truncation=False)["input_ids"]
    df["n_tokens"] = [len(x) for x in ids]
    df["over_512"] = df["n_tokens"] > 512
    return df


for name, (fname, code_col, lang_col) in DATASETS.items():
    path = DATA / fname
    out = ROOT / "data" / "interim" / f"{name}_token_lengths.parquet"

    print(f"\n=== {name} ({path}) ===")

    # Skip if output already exists
    if out.exists():
        print(f"Output already exists at {out}, skipping.")
        continue

    if not path.exists():
        print("FILE NOT FOUND, skipping")
        continue

    df = token_stats(path, code_col, lang_col)
    print("\nrows per language:")
    print(df[lang_col].value_counts())
    print("\n% over 512 per language:")
    print(df.groupby(lang_col)["over_512"].mean().mul(100).round(1))
    print("\n% over 512 by label (0=clean, 1=vulnerable):")
    print(df.groupby("label")["over_512"].mean().mul(100).round(1))
    print("\ntoken count summary:")
    print(df["n_tokens"].describe(percentiles=[0.5, 0.75, 0.9, 0.95, 0.99]).round(0))

    out.parent.mkdir(parents=True, exist_ok=True)  # ensures output folder exists
    df[[lang_col, "label", "n_tokens", "over_512"]].to_parquet(out)
