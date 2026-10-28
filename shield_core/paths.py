"""Single source of truth for where things live on disk.

Every module that needs the repository root, a data folder or a docs folder imports it from
here. Nothing may compute the root by counting `.parent`s from `__file__` any more: that
silently breaks the day a file is moved (this is why the 2026-10 refactor added this module).

Two kinds of folders:
  * tracked   : docs/, tests/fixtures/       (committed to git)
  * generated : data/, model_artifacts/      (git-ignored, created at run time)
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# --- generated, git-ignored ---------------------------------------------------------
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"  # downloaded datasets, untouched
INTERIM_DIR = DATA_DIR / "interim"  # unified-schema parquet, deduped, merged
SPLITS_DIR = INTERIM_DIR / "splits"  # train / val / test / holdout
CACHE_DIR = DATA_DIR / "cache"  # embedding + commit-lookup caches
GRAPH_CACHE_DIR = CACHE_DIR / "graphs"  # Joern graphs keyed by code hash + versions
MODEL_ARTIFACTS_DIR = REPO_ROOT / "model_artifacts"  # files the model registry loads
TRAIN_RUNS_DIR = MODEL_ARTIFACTS_DIR / "train_runs"  # output of scripts/training/train_v1.py
BENCHMARK_DIR = INTERIM_DIR / "joern_benchmark"  # Joern extraction benchmark results
JOERN_TRIAGE_DIR = INTERIM_DIR / "joern_triage"  # Raw graphs and reports for W2-P2-04

# --- tracked: documentation, grouped by topic ----------------------------------------
DOCS_DIR = REPO_ROOT / "docs"
DOCS_API_DIR = DOCS_DIR / "api"
DOCS_DATASETS_DIR = DOCS_DIR / "datasets"
DOCS_AUDITS_DIR = DOCS_DATASETS_DIR / "audits"  # dataset_audit, dedupe_report, manifest
DOCS_EXPLORATION_DIR = DOCS_DATASETS_DIR / "exploration"  # per-dataset exploration reports
DOCS_LEAKAGE_DIR = DOCS_DATASETS_DIR / "leakage"
DOCS_PROJECT_NAMES_DIR = DOCS_DATASETS_DIR / "project_names"  # alias json + review csvs
DOCS_GRAPHS_DIR = DOCS_DIR / "graphs"
DOCS_TAINT_DIR = DOCS_DIR / "taint"
DOCS_FIXES_DIR = DOCS_DIR / "fixes"
DOCS_MODELING_DIR = DOCS_DIR / "modeling"

# --- tracked: tests ------------------------------------------------------------------
TESTS_DIR = REPO_ROOT / "tests"
FIXTURES_DIR = TESTS_DIR / "fixtures"
