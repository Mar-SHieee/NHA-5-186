"""Write the per-CWE (or per-family) table for one training run (W2-P3-03).

Run from the project root:
    python -m scripts.training.per_cwe_table model_artifacts/train_runs/<run_folder>
    python -m scripts.training.per_cwe_table model_artifacts/train_runs/<run_folder> --families
"""

import json
import sys
from pathlib import Path

import pandas as pd

from shield_core.eval.metrics import (
    _pick_true_cwe,
    commits_per_cwe,
    per_cwe_metrics_by_language,
)

FAMILY_MAP = Path("scripts/training/cwe_family_map.json")
SPLIT_QA_CWE = Path("docs/datasets/audits/split_qa_cwe.csv")


def split_qa_cells(split_qa, cwe):
    """Rows in train / val / test and commit groups for one CWE, from split QA."""
    info = split_qa.get(cwe)
    if info is None:
        return " - | - | - | - |"
    return (
        f" {int(info['rows_train'])} | {int(info['rows_val'])} | {int(info['rows_test'])}"
        f" | {int(info['commit_groups'])} |"
    )


def main():
    run_dir = Path(sys.argv[1])
    by_family = "--families" in sys.argv
    out_path = Path(
        "docs/modeling/v1_per_family.md" if by_family else "docs/modeling/v1_per_cwe.md"
    )
    df = pd.read_parquet(run_dir / "predictions_test.parquet")
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    model_cwes = set(metrics["cwe_classes"])

    # The CWE only means something on truly vulnerable rows
    df = df[(df["label"] == 1) & (df["cwe_all"].map(len) > 0)].reset_index(drop=True)

    # CWEs the model never learned are scored as "Other", the same way as metrics.json
    y_true = [[c if c in model_cwes else "Other" for c in cwes] for cwes in df["cwe_all"]]
    y_pred = df["pred_cwe"].tolist()

    # Optional: score families (memory_safety, input_injection, ...) instead of exact CWEs
    if by_family:
        spec = json.loads(FAMILY_MAP.read_text(encoding="utf-8"))
        to_family, fallback = spec["cwe_to_family"], spec["fallback_family"]
        y_true = [[to_family.get(c, fallback) for c in cwes] for cwes in df["cwe_all"]]
        y_pred = [to_family.get(c, fallback) for c in y_pred]
    languages = df["language"].tolist()

    results = per_cwe_metrics_by_language(y_true, y_pred, languages)

    # Rows per split and commit groups per CWE, from the split QA tool (W2-P5-04)
    split_qa = {}
    if not by_family and SPLIT_QA_CWE.exists():
        split_qa = pd.read_csv(SPLIT_QA_CWE).set_index("cwe").to_dict("index")

    lines = [
        f"# V1 per-{'family' if by_family else 'CWE'} results (test split)",
        "",
        f"Run: `{run_dir.name}`. Only rows with label = 1 are scored.",
        "Not final: split QA is not green yet (see `docs/datasets/audits/split_qa.md`, D33).",
        "`reliable = no` means fewer than 3 commits for that CWE, so do not quote its numbers.",
        "A CWE is listed if it is the true CWE of a test row, or if the model predicted it.",
        "`support = 0` means the model predicted that CWE, but no test row has it.",
    ]
    if split_qa:
        lines += [
            "`train / val / test rows` and `groups` come from split QA (`split_qa_cwe.csv`):",
            "all languages, and every row tagged with the CWE (label 0 too), so they are",
            "bigger than `support`. `-` means the CWE is not in split QA (for example Other).",
        ]
    lines.append("")

    for language, rows in results.items():
        lang_rows = df["language"] == language
        # Same rule as the metrics, so support and commits count the same rows
        true_cwe = [
            _pick_true_cwe(t, p)
            for t, p, keep in zip(y_true, y_pred, lang_rows, strict=True)
            if keep
        ]
        commits = commits_per_cwe(true_cwe, df.loc[lang_rows, "commit"].tolist())

        name = "family" if by_family else "CWE"
        header = f"| {name} | support | commits | reliable | precision | recall | f1 |"
        divider = "| --- | --- | --- | --- | --- | --- | --- |"
        if split_qa:
            header += " train rows | val rows | test rows | groups |"
            divider += " --- | --- | --- | --- |"
        lines += [f"## {language}", "", header, divider]

        for row in sorted(rows, key=lambda r: r["support"], reverse=True):
            info = commits.get(row["cwe"], {"commits": 0, "reliable": False})
            line = (
                f"| {row['cwe']} | {row['support']} | {info['commits']} "
                f"| {'yes' if info['reliable'] else 'no'} "
                f"| {row['precision']:.3f} | {row['recall']:.3f} | {row['f1']:.3f} |"
            )
            if split_qa:
                line += split_qa_cells(split_qa, row["cwe"])
            lines.append(line)
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
