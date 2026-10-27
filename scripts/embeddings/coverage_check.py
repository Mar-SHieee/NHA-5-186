from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
names = ["bigvul_deduped", "megavul_deduped", "cvefixes_python_deduped", "cvefixes_cpp_deduped"]
caps = [512, 1024, 2048, 4096, 8192]

rows = []
for name in names:
    df = pd.read_parquet(ROOT / "data" / "interim" / f"{name}_token_lengths.parquet")
    row = {"dataset": name, "rows": len(df)}
    for cap in caps:
        row[f"<= {cap}"] = round((df["n_tokens"] <= cap).mean() * 100, 1)
    # same coverage for the vulnerable class only, since it is the one that matters
    vul = df[df["label"] == 1]
    row["vul <= 4096"] = round((vul["n_tokens"] <= 4096).mean() * 100, 1)
    rows.append(row)

print(pd.DataFrame(rows).to_string(index=False))
