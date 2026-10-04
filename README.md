# SHIELD

**S**emantic and **H**ierarchical **I**nference for **E**xploits and **L**ogic **D**etection.

A vulnerability detection system combining CodeBERT, graph neural networks, and a verified fix loop. The full roadmap, decisions, and task list live in [`SHIELD_PLAN.md`](SHIELD_PLAN.md), which is the single source of truth.

## Prerequisites

- Git and a GitHub account
- Python 3.10 or newer (the team will standardize on one version; check `SHIELD_PLAN.md`)

## Getting started (team contributors)

If you have write access to this repo, work on branches in the main repo.

```bash
# 1. Clone
git clone https://github.com/nhahub/NHA-5-186.git
cd NHA-5-186

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate       # macOS / Linux

# 3. Install the project with dev tools
pip install -e ".[dev]"

# 4. Install the git hooks (one time per clone)
pre-commit install

# 5. Verify your setup (all four should pass)
ruff check .
ruff format --check .
pytest
pre-commit run --all-files
```

If PowerShell blocks the activate script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

## Daily workflow

Never commit directly to `main`. Every change goes through a branch and a pull request.

```bash
git checkout main
git pull
git checkout -b w1-p2-pyg-setup     # w<week>-p<person>-<topic>
# ... make changes, commit ...
git push -u origin w1-p2-pyg-setup
```

Then open a pull request on GitHub:

- Put the task ID in the title (for example `W1-P2-01: set up PyTorch Geometric`).
- Wait for CI to pass (lint, format check, tests).
- Get approval from your assigned reviewer (see Section 5 of `SHIELD_PLAN.md`).
- Merge once both are done.

## Contributing from a fork

Use this route only if you do not have write access to the main repo.

```bash
# 1. Fork the repo on GitHub, then clone YOUR fork
git clone https://github.com/<your-username>/NHA-5-186.git
cd NHA-5-186

# 2. Add the original repo as "upstream"
git remote add upstream https://github.com/nhahub/NHA-5-186.git
git remote -v        # origin = your fork, upstream = the original
```

Then follow steps 2 to 5 of "Getting started" above (virtual environment, install, `pre-commit install`, verify).

Before starting each new branch, sync your fork with the original:

```bash
git checkout main
git fetch upstream
git merge upstream/main
git push origin main
git checkout -b w1-p2-pyg-setup
```

Push your branch to your fork (`origin`) and open a pull request from your fork's branch into `main` of the original repo. The same rules apply: task ID in the title, green CI, and an approval before merge. For a first-time fork contributor, a maintainer may need to click "Approve and run" before CI starts.

## Project checks

| Tool | Purpose | Command |
| --- | --- | --- |
| Ruff (lint) | Finds bugs and style problems | `ruff check .` (add `--fix` to auto-fix) |
| Ruff (format) | Enforces code style | `ruff format .` (CI uses `--check`) |
| pytest | Runs tests in `tests/` | `pytest` |
| pre-commit | Runs checks automatically on each commit | `pre-commit run --all-files` |

CI runs the lint, format check, and tests on every pull request and on every push to `main`. Pre-commit is your fast local check, and CI is the enforced one.

## Troubleshooting

- **Commit aborted by pre-commit:** a hook probably reformatted files. Run `git add .` and commit again.
- **`ruff` or `pytest` not found:** your virtual environment is not active.
- **CI fails but passes locally:** run `ruff format --check .` and make sure your Python version matches CI.
- **Push rejected:** run `git pull` first, because your local branch is behind.

## Repository layout

```
.github/            CI workflow and PR template
shield_core/        the core library
tests/              unit tests
SHIELD_PLAN.md      plan, decisions, and task checklist
pyproject.toml      package metadata and tool settings
```

More folders (`languages/`, `docs/`, `api/`, `web/`) are added by later tasks; see Section 4.3 of the plan.
