"""
W2-P3-01 - XGBoost V1 (Python only): binary + CWE, calibrated, logged to MLflow.
Run:  python scripts/training/train_v1.py
"""

import hashlib
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    matthews_corrcoef,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

# ---------------- Config ----------------
CONFIG = {
    "seed": 42,
    "manifest": "docs/datasets/audits/dataset_manifest_v0.json",
    "splits_dir": "data/interim/splits",
    "language": "python",
    "use_fixed_code_as_negatives": True,
    "min_cwe_count": 20,
    "cwe_grouping": False,
    "model": "logreg",
    "logreg_C": 1.0,
    "features": "tfidf",
    "only_rows_with_precomputed": False,
    "precomputed": [
        (
            "data/interim/cvefixes_python_deduped.parquet",
            "data/interim/cvefixes_python_deduped_embeddings.npy",
        ),
        (
            "data/interim/zenodo_python_deduped.parquet",
            "data/interim/zenodo_python_deduped_embeddings.npy",
        ),
    ],
    "embeddings_dir": "data/interim/v1_embeddings",
    "xgb": {
        "n_estimators": 2000,
        "learning_rate": 0.05,
        "max_depth": 6,
        "subsample": 0.8,
        "colsample_bytree": 0.4,
        "early_stopping_rounds": 100,
    },
}
SEED = CONFIG["seed"]
np.random.seed(SEED)
OUT = f"model_artifacts/train_runs/{CONFIG['model']}_v1_{datetime.now():%Y%m%d_%H%M%S}"
os.makedirs(OUT, exist_ok=True)


# CWE groups (used when "cwe_grouping" is True). CWEs not listed here -> "Other".
CWE_GROUPS = {
    "Injection": [74, 77, 78, 79, 80, 88, 89, 90, 91, 93, 94, 95, 116, 117, 917, 1336],
    "Path/File": [21, 22, 23, 36, 59, 73, 377, 426, 427, 434, 552],
    "Auth/Access": [
        250,
        269,
        276,
        284,
        285,
        287,
        290,
        306,
        307,
        346,
        352,
        384,
        521,
        613,
        620,
        639,
        640,
        732,
        862,
        863,
        1021,
    ],
    "Info leak": [200, 201, 203, 209, 215, 312, 319, 359, 522, 532, 538],
    "Web request": [113, 444, 601, 918],
    "Resource/DoS": [400, 407, 409, 674, 770, 789, 834, 835, 1333],
    "Crypto/Cert": [
        295,
        310,
        311,
        320,
        325,
        326,
        327,
        330,
        331,
        335,
        337,
        338,
        345,
        347,
    ],
    "Deserialization": [502],
    "Memory": [119, 120, 121, 122, 125, 131, 190, 191, 401, 415, 416, 476, 787],
    "Input validation": [20, 129, 707, 1284, 1287],
}
CWE_TO_GROUP = {f"CWE-{n}": group for group, nums in CWE_GROUPS.items() for n in nums}


# ---------------- 1. Load data ----------------
def first_cwe(x):
    cwes = [str(c) for c in (x if x is not None else []) if str(c).startswith("CWE-")]
    if not cwes:
        return None
    return CWE_TO_GROUP.get(cwes[0], "Other") if CONFIG["cwe_grouping"] else cwes[0]


def load(split):
    df = pd.read_parquet(f"{CONFIG['splits_dir']}/{split}.parquet")
    df = df[df["language"] == CONFIG["language"]].copy()
    df["cwe"] = df["cwe"].apply(first_cwe)

    if CONFIG["use_fixed_code_as_negatives"]:
        fixed = df[
            (df["label"] == 1) & df["fixed_code"].notna() & (df["fixed_code"] != df["code"])
        ].copy()
        fixed["code"], fixed["label"], fixed["cwe"] = fixed["fixed_code"], 0, None
        df = pd.concat([df, fixed])

    df = df.drop_duplicates("code")
    df["label"] = df["label"].astype(int)
    print(f"{split:5s}: {len(df)} rows | positives {df['label'].mean():.1%}")
    return df.reset_index(drop=True)


train, val, test = load("train"), load("val"), load("test")
# drop test/val rows whose code also appears in train
val = val[~val["code"].isin(train["code"])].reset_index(drop=True)
test = test[~test["code"].isin(train["code"]) & ~test["code"].isin(val["code"])].reset_index(
    drop=True
)


# ---------------- 1b. Ready embeddings: match split rows by their code ----------------
def code_key(code):
    return hashlib.sha1(" ".join(str(code).split()).encode("utf-8", "ignore")).hexdigest()


USE_PRE = "precomputed" in CONFIG["features"] or CONFIG["only_rows_with_precomputed"]
if USE_PRE:
    lookup = {}
    for parquet_path, npy_path in CONFIG["precomputed"]:
        codes = pd.read_parquet(parquet_path, columns=["code"])["code"]
        matrix = np.load(npy_path)
        assert len(codes) == len(matrix), (
            f"{parquet_path} and {npy_path} have different row counts!"
        )
        for code, vector in zip(codes, matrix, strict=True):
            if np.any(vector):
                lookup[code_key(code)] = vector

    def keep_matched(df, split):
        keys = df["code"].map(code_key)
        found = keys.isin(lookup.keys())
        print(
            f"{split:5s}: {found.sum()}/{len(df)} rows have a ready embedding "
            f"| positives {df.loc[found, 'label'].mean():.1%}"
        )
        df = df[found].reset_index(drop=True)
        df["emb_key"] = keys[found].values
        return df

    print("\nMatching rows to ready embeddings (rows without one are dropped):")
    train, val, test = (
        keep_matched(train, "train"),
        keep_matched(val, "val"),
        keep_matched(test, "test"),
    )


# ---------------- 2. Features (fit on train only) ----------------
def codebert_embeddings(codes, split):
    """Your window CodeBERT embeddings (mean of windows), saved per split."""
    key = hashlib.sha1("\n".join(codes).encode("utf-8", "ignore")).hexdigest()[:10]
    path = f"{CONFIG['embeddings_dir']}/{split}_{CONFIG['language']}_{key}.npy"
    if os.path.exists(path):
        return np.load(path)

    sys.path.insert(0, os.getcwd())
    from scripts.embeddings.long_embedding import process_dataset
    from shield_core.embeddings.embedder import CodeBERTEmbedder

    print(f"Computing CodeBERT embeddings for {split} ({len(codes)} functions)...")
    embedder = CodeBERTEmbedder(cache_dir="data/cache")
    _, matrix = process_dataset(pd.DataFrame({"code": codes}), embedder)
    os.makedirs(CONFIG["embeddings_dir"], exist_ok=True)
    np.save(path, matrix)
    return matrix


parts = {"train": [], "val": [], "test": []}
data = {"train": train, "val": val, "test": test}

vec = None
if CONFIG["features"] in ("tfidf", "both", "tfidf+precomputed"):
    vec = TfidfVectorizer(
        token_pattern=r"[A-Za-z_]\w*|\d+|[^\s\w]",
        lowercase=False,
        ngram_range=(1, 2),
        min_df=2,
        max_features=50000,
    )
    parts["train"].append(vec.fit_transform(train["code"]))
    parts["val"].append(vec.transform(val["code"]))
    parts["test"].append(vec.transform(test["code"]))

if CONFIG["features"] in ("embeddings", "both"):
    for split, df in data.items():
        parts[split].append(sp.csr_matrix(codebert_embeddings(df["code"].tolist(), split)))

if "precomputed" in CONFIG["features"]:
    for split, df in data.items():
        parts[split].append(sp.csr_matrix(np.vstack([lookup[k] for k in df["emb_key"]])))

X_train, X_val, X_test = (sp.hstack(parts[s], format="csr") for s in ["train", "val", "test"])
print(f"Features: {CONFIG['features']} -> {X_train.shape[1]} columns")


# ---------------- 3. Binary model ----------------
def binary_metrics(y, p, thr):
    pred = (p >= thr).astype(int)
    return {
        "roc_auc": roc_auc_score(y, p),
        "pr_auc": average_precision_score(y, p),
        "precision": precision_score(y, pred, zero_division=0),
        "recall": recall_score(y, pred),
        "f1": f1_score(y, pred),
        "mcc": matthews_corrcoef(y, pred),
        "brier": brier_score_loss(y, p),
    }


y_train, y_val, y_test = train["label"].values, val["label"].values, test["label"].values


def make_model(multiclass=False):
    if CONFIG["model"] == "logreg":
        return LogisticRegression(C=CONFIG["logreg_C"], max_iter=3000, random_state=SEED)
    extra = (
        {"objective": "multi:softprob", "eval_metric": "mlogloss"}
        if multiclass
        else {"eval_metric": "logloss"}
    )
    return XGBClassifier(**CONFIG["xgb"], **extra, random_state=SEED, n_jobs=-1)


def fit_model(model, X, y, X_es, y_es):
    weights = compute_sample_weight("balanced", y)
    if CONFIG["model"] == "logreg":
        return model.fit(X, y, sample_weight=weights)
    return model.fit(X, y, sample_weight=weights, eval_set=[(X_es, y_es)], verbose=False)


print(f"\nModel: {CONFIG['model']}")
binary = fit_model(make_model(), X_train, y_train, X_val, y_val)

# Calibration (isotonic, fit on val)
p_val_raw = binary.predict_proba(X_val)[:, 1]
p_test_raw = binary.predict_proba(X_test)[:, 1]
calibrator = IsotonicRegression(out_of_bounds="clip").fit(p_val_raw, y_val)
p_val, p_test = calibrator.predict(p_val_raw), calibrator.predict(p_test_raw)

# Threshold that maximizes MCC on val
thresholds = np.unique(np.quantile(p_val, np.linspace(0.01, 0.99, 99)))
threshold = float(max(thresholds, key=lambda t: matthews_corrcoef(y_val, (p_val >= t).astype(int))))

binary_test = binary_metrics(y_test, p_test, threshold)
print(
    "\nBINARY TEST:",
    {k: round(v, 4) for k, v in binary_test.items()},
    f"| threshold {threshold:.3f}",
)
print(
    f"Brier raw {brier_score_loss(y_test, p_test_raw):.4f} -> calibrated {binary_test['brier']:.4f}"
)
for src in test["source"].unique():
    m = (test["source"] == src).values
    if len(set(y_test[m])) > 1:
        mcc_val = matthews_corrcoef(y_test[m], (p_test[m] >= threshold).astype(int))
        print(f"  {src}: MCC {mcc_val:.3f}")

# Calibration plot data (CSV only)
bins = np.clip((p_test * 10).astype(int), 0, 9)
calib = (
    pd.DataFrame({"bin": bins, "pred": p_test, "true": y_test})
    .groupby("bin")
    .agg(
        count=("true", "size"),
        mean_predicted=("pred", "mean"),
        fraction_positive=("true", "mean"),
    )
)
calib.to_csv(f"{OUT}/calibration_plot_data.csv")


# ---------------- 4. CWE model (vulnerable rows only) ----------------
def cwe_rows(df, X):
    m = ((df["label"] == 1) & df["cwe"].notna()).values
    return X[m], df.loc[m, "cwe"]


Xc_train, c_train = cwe_rows(train, X_train)
Xc_val, c_val = cwe_rows(val, X_val)
Xc_test, c_test = cwe_rows(test, X_test)

counts = c_train.value_counts()
classes = sorted(c for c in counts[counts >= CONFIG["min_cwe_count"]].index if c != "Other") + [
    "Other"
]


def to_id(s):
    return s.where(s.isin(classes), "Other").map({c: i for i, c in enumerate(classes)}).values


yc_train, yc_val, yc_test = to_id(c_train), to_id(c_val), to_id(c_test)

cwe = fit_model(make_model(multiclass=True), Xc_train, yc_train, Xc_val, yc_val)
pc_test = cwe.predict(Xc_test)
cwe_test = {
    "accuracy": float((pc_test == yc_test).mean()),
    "macro_f1": f1_score(yc_test, pc_test, average="macro"),
    "weighted_f1": f1_score(yc_test, pc_test, average="weighted"),
}
print(
    f"\nCWE TEST ({len(classes)} classes{', grouped' if CONFIG['cwe_grouping'] else ''}): {classes}"
)
print("CWE TEST:", {k: round(v, 4) for k, v in cwe_test.items()})

# # ---------------- 5. Save V1 artifact + MLflow ----------------
# binary.save_model(f"{OUT}/binary_model.json")
# cwe.save_model(f"{OUT}/cwe_model.json")
# joblib.dump(
#     {
#         "vectorizer": vec,
#         "calibrator": calibrator,
#         "threshold": threshold,
#         "cwe_classes": classes,
#         "cwe_groups": CWE_GROUPS if CONFIG["cwe_grouping"] else None,
#     },
#     f"{OUT}/preprocessing.joblib",
# )
# with open(f"{OUT}/config.json", "w") as f:
#     json.dump(CONFIG, f, indent=2)
# with open(f"{OUT}/metrics.json", "w") as f:
#     json.dump(
#         {"binary_test": binary_test, "threshold": threshold, "cwe_test": cwe_test},
#         f,
#         indent=2,
#         default=float,
#     )

# manifest = json.load(open(CONFIG["manifest"], encoding="utf-8"))
# mlflow.set_tracking_uri("sqlite:///mlflow.db")
# mlflow.set_experiment("W2-P3-01_xgboost")
# with mlflow.start_run(run_name=os.path.basename(OUT)):
#     mlflow.set_tags(
#         {
#             "manifest_version": manifest.get("manifest_version"),
#             "dataset_hash": manifest.get("dataset_hash"),
#         }
#     )
#     mlflow.log_params(
#         {
#             "seed": SEED,
#             "threshold": threshold,
#             "language": CONFIG["language"],
#             "features": CONFIG["features"],
#             "cwe_grouping": CONFIG["cwe_grouping"],
#             "fixed_code_negatives": CONFIG["use_fixed_code_as_negatives"],
#             **CONFIG["xgb"],
#         }
#     )
#     mlflow.log_metrics({f"binary_{k}": float(v) for k, v in binary_test.items()})
#     mlflow.log_metrics({f"cwe_{k}": float(v) for k, v in cwe_test.items()})
#     mlflow.log_artifacts(OUT)

# print(f"\nSaved to {OUT} and logged to MLflow")
