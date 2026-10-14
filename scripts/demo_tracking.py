"""Demo run for the run-logging helper (W1-P5-03).

    python scripts/demo_tracking.py                   # prints to the console
    python scripts/demo_tracking.py --backend mlflow  # writes to ./mlruns
    python scripts/demo_tracking.py --backend wandb   # needs `wandb login` or WANDB_API_KEY

Running it twice with the same seed gives the same loss curve and the same dataset hash.
"""

from __future__ import annotations

import argparse
import random
import tempfile
from pathlib import Path

from shield_core.tracking import start_run


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo of shield_core.tracking")
    parser.add_argument("--backend", choices=["console", "mlflow", "wandb"], default=None)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    config = {
        "model": "toy-gnn",
        "lr": 0.01,
        "epochs": 5,
        "optimizer": {"name": "adam", "weight_decay": 0.0},
    }
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "toy.csv"
        data.write_bytes(b"id,label\n1,0\n2,1\n3,0\n")  # bytes: same hash on every OS
        with start_run(
            config,
            seed=args.seed,
            dataset_path=data,
            backend=args.backend,
            run_name="demo",
        ) as run:
            loss = 1.0
            for epoch in range(config["epochs"]):
                loss *= 0.7 + 0.05 * random.random()
                run.log_metrics({"loss": loss}, step=epoch)
            print(f"backend={run.backend_name} dataset_hash={run.params['dataset_hash']}")
            if run.url:
                print(f"run page: {run.url}")


if __name__ == "__main__":
    main()
