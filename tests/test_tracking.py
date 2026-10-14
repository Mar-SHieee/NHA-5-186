import hashlib
import random
from types import SimpleNamespace

import pytest

from shield_core import tracking


@pytest.fixture(autouse=True)
def _no_tracker_env(monkeypatch):
    monkeypatch.delenv(tracking.BACKEND_ENV, raising=False)


# ------------------------------------------------------------------ hashing


def test_hash_file_matches_hashlib_and_reads_in_chunks(tmp_path):
    data = bytes(range(256)) * 50
    f = tmp_path / "d.bin"
    f.write_bytes(data)
    assert tracking.hash_file(f, chunk_size=100) == hashlib.sha256(data).hexdigest()


def test_hash_dataset_ignores_file_name_but_not_content(tmp_path):
    (tmp_path / "a.csv").write_bytes(b"1,2,3\n")
    (tmp_path / "b.csv").write_bytes(b"1,2,3\n")
    (tmp_path / "c.csv").write_bytes(b"1,2,4\n")
    same = tracking.hash_dataset(tmp_path / "a.csv") == tracking.hash_dataset(tmp_path / "b.csv")
    assert same
    assert tracking.hash_dataset(tmp_path / "a.csv") != tracking.hash_dataset(tmp_path / "c.csv")
    assert tracking.hash_dataset(tmp_path / "a.csv").startswith("sha256:")


def test_hash_dataset_folder_depends_on_names_and_content(tmp_path):
    one = tmp_path / "one"
    two = tmp_path / "two"
    for folder, name in ((one, "x.txt"), (two, "y.txt")):
        folder.mkdir()
        (folder / name).write_bytes(b"same")
    assert tracking.hash_dataset(one) != tracking.hash_dataset(two)
    assert tracking.hash_dataset(one) == tracking.hash_dataset(one)


def test_hash_dataset_missing_path_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        tracking.hash_dataset(tmp_path / "nope")


# ------------------------------------------------------------------ seed


def test_same_seed_gives_same_random_numbers():
    tracking.set_seed(7)
    first = [random.random() for _ in range(3)]
    tracking.set_seed(7)
    assert [random.random() for _ in range(3)] == first


def test_seed_also_seeds_numpy():
    numpy = pytest.importorskip("numpy")
    tracking.set_seed(7)
    first = numpy.random.rand(3).tolist()
    tracking.set_seed(7)
    assert numpy.random.rand(3).tolist() == first


# ------------------------------------------------------------------ start_run rules


def test_exactly_one_dataset_source_is_required(tmp_path):
    with pytest.raises(ValueError, match="exactly one"):
        tracking.start_run({}, seed=1)
    f = tmp_path / "d.csv"
    f.write_bytes(b"x")
    with pytest.raises(ValueError, match="exactly one"):
        tracking.start_run({}, seed=1, dataset_path=f, dataset_hash="sha256:abc")


def test_reserved_config_keys_are_rejected():
    with pytest.raises(ValueError, match="reserved"):
        tracking.start_run({"seed": 1}, seed=1, dataset_hash="none")


def test_unknown_backend_is_rejected():
    with pytest.raises(ValueError, match="unknown backend"):
        tracking.start_run({}, seed=1, dataset_hash="none", backend="tensorboard")


def test_console_run_logs_params_seed_hash_and_metrics(tmp_path, capsys):
    f = tmp_path / "d.csv"
    f.write_bytes(b"a,b\n1,2\n")
    config = {"lr": 0.1, "opt": {"name": "adam"}, "layers": [1, 2]}

    with tracking.start_run(config, seed=5, dataset_path=f) as run:
        run.log_metrics({"loss": 0.5}, step=3)

    assert run.params["seed"] == 5
    assert run.params["opt.name"] == "adam"
    assert run.params["layers"] == "[1, 2]"
    assert run.params["dataset_hash"] == tracking.hash_dataset(f)
    out = capsys.readouterr().out
    assert "seed = 5" in out
    assert "dataset_hash = sha256:" in out
    assert "step=3" in out
    assert "finished" in out


def test_precomputed_hash_is_logged_without_reading_anything():
    run = tracking.start_run({}, seed=1, dataset_hash="sha256:abc123")
    assert run.params["dataset_hash"] == "sha256:abc123"
    run.finish()


def test_finish_is_safe_to_call_twice(capsys):
    run = tracking.start_run({}, seed=1, dataset_hash="none")
    run.finish()
    run.finish()
    assert capsys.readouterr().out.count("finished") == 1


def test_env_variable_picks_the_backend(monkeypatch):
    monkeypatch.setenv(tracking.BACKEND_ENV, "mlflow")
    monkeypatch.setattr(tracking, "_require", lambda name: pytest.fail("should be mocked"))
    with pytest.raises(pytest.fail.Exception):
        tracking.start_run({}, seed=1, dataset_hash="none")


def test_missing_package_gives_a_clear_install_hint():
    with pytest.raises(ImportError, match="pip install"):
        tracking._require("definitely_not_a_real_package_xyz")


# ------------------------------------------------------------------ backends (fake libraries)


def test_wandb_backend_calls(monkeypatch):
    calls = []
    run = SimpleNamespace(
        url="https://example.test/run",
        config=SimpleNamespace(update=lambda p: calls.append(("config", p))),
        log=lambda metrics, step=None: calls.append(("log", metrics, step)),
        finish=lambda: calls.append(("finish",)),
    )
    fake = SimpleNamespace(init=lambda project, name: run)
    monkeypatch.setattr(tracking, "_require", lambda name: fake)

    with tracking.start_run({"lr": 1}, seed=2, dataset_hash="none", backend="wandb") as logged:
        logged.log_metrics({"loss": 1.0}, step=0)

    assert logged.url == "https://example.test/run"
    assert calls[0] == ("config", {"lr": 1, "seed": 2, "dataset_hash": "none"})
    assert calls[1] == ("log", {"loss": 1.0}, 0)
    assert calls[-1] == ("finish",)


def test_mlflow_backend_calls(monkeypatch):
    calls = []
    fake = SimpleNamespace(
        set_experiment=lambda name: calls.append(("experiment", name)),
        start_run=lambda run_name=None: calls.append(("start", run_name)),
        log_params=lambda p: calls.append(("params", p)),
        log_metrics=lambda m, step=None: calls.append(("metrics", m, step)),
        end_run=lambda: calls.append(("end",)),
    )
    monkeypatch.setattr(tracking, "_require", lambda name: fake)

    with tracking.start_run({}, seed=2, dataset_hash="none", backend="mlflow", run_name="r") as run:
        run.log_metrics({"loss": 1.0}, step=1)

    assert calls[0] == ("experiment", tracking.DEFAULT_PROJECT)
    assert calls[1] == ("start", "r")
    assert calls[2] == ("params", {"seed": 2, "dataset_hash": "none"})
    assert calls[3] == ("metrics", {"loss": 1.0}, 1)
    assert calls[-1] == ("end",)
