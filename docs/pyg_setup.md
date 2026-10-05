# PyG setup and toy GNN (W1-P2-01)

Install recipe for PyTorch + PyTorch Geometric, plus a toy GNN run that proves the
setup works. Tested versions are listed below. If you use other versions, record them.

## Tested configuration

| Item | Machine 1 | Machine 2 |
|---|---|---|
| OS | Windows 11 | TODO |
| GPU | RTX 4060 Laptop, 8 GB | TODO |
| NVIDIA driver | 560.94 (supports CUDA 12.6) | TODO |
| Python | 3.12.0 | TODO |
| torch | 2.14.1+cu126 | TODO |
| torch_geometric | 2.8.0.post1 | TODO |

## 1. Choose your PyTorch build

You do **not** need to install the CUDA Toolkit. The PyTorch wheel bundles its own CUDA
runtime. You only need an NVIDIA driver new enough for the wheel.

Run `nvidia-smi` and read "CUDA Version" (top right). It is the highest CUDA version your
driver supports.

| Your machine | Use |
|---|---|
| NVIDIA GPU, CUDA Version 12.6 or higher | `requirements/torch-cu126.txt` |
| NVIDIA GPU, older driver | Update the driver, or pick an older build from the PyTorch Get Started page |
## 2. Install

Use Python 3.12 and a fresh virtual environment (keep it outside OneDrive).

```powershell
py -3.12 -m venv C:\venvs\shield-pyg
C:\venvs\shield-pyg\Scripts\Activate.ps1

# from the repo root; torch FIRST so pip does not replace it with the CPU build
python -m pip install -r requirements\torch-cu126.txt
python -m pip install -e ".[gnn,dev]"
```

`requirements/torch-cu126.txt`:
```
--index-url https://download.pytorch.org/whl/cu126
torch==2.14.1
```
Keep only torch in this file: `--index-url` replaces PyPI for everything listed in it.

## 3. Verify

```powershell
python scripts\check_env.py
python scripts\toy_gnn.py
```

Expected from `check_env.py`: `cuda avail: True`, your GPU name, and a `pyg` version.
A `FutureWarning` about `torch.jit.script` comes from PyG and is harmless.

Expected from `toy_gnn.py`: MUTAG downloads on first run (into `data/TUDataset`, git-ignored),
then test accuracy lands around 0.74 to 0.79. The test set has 38 graphs, so one graph is
about 2.6 points of noise.

## 4. Toy run results (seed 0)

| Item | Machine 1 | Machine 2 |
|---|---|---|
| Final train / test accuracy | 0.760 / 0.763 | TODO |
| Training time (100 epochs) | 4.6 s | TODO |
| Peak VRAM | 17.2 MB | TODO |

Model: 2x GCNConv (hidden 32) -> global mean pool -> Linear. Dataset: MUTAG, 150/38 split.

## 5. If something fails

- **`cuda avail: False` on a machine with an NVIDIA GPU.** A CPU-only torch was installed,
  or the driver is too old. Reinstall torch from the CUDA requirements file with
  `--force-reinstall`, then run `check_env.py` again.
- **`No module named 'torch'`.** The `python` you ran is not the one pip installed into.
  Use `python -m pip ...` and check `python -c "import sys; print(sys.executable)"`.
- **Red squiggles in PyCharm.** Set the project interpreter to the venv's `python.exe`.
- **`import torch_geometric` fails.** Install the extra: `python -m pip install -e ".[gnn]"`.
- **Slow or locked installs.** Do not create the venv inside a OneDrive folder.

## Notes

- Older PyG helper packages (`torch-scatter`, `torch-sparse`) are not needed here. Add them
  only if an error asks for them.
- The `gnn` extra is optional so CI (which installs `.[dev]`) is unaffected.
- Python version: tested on 3.12; CI currently uses 3.11. Both satisfy `requires-python`.
