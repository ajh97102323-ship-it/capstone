"""surrogate/tune.py 테스트 (specs/002 T010, research R7)."""
import copy
import json

import numpy as np
import pytest

from data.io import load_dataset
from surrogate import load_surrogate
from surrogate import tune as tu

SPACE = {"n_layers": (1, 2), "width": (4, 8), "lr": (1e-3, 1e-2), "batch": (32, 64), "alpha": (1e-6, 1e-3)}
KW = dict(n_trials=3, seed=0, space=SPACE, max_epochs=5, patience=3)


def test_tuning_json_best_and_saved_model(small_dataset, tmp_path):
    p = tu.tune_and_save(small_dataset, tmp_path, "t1", report=False, **KW)
    assert p == tmp_path / "t1"
    tj = json.loads((p / "tuning.json").read_text(encoding="utf-8"))
    assert tj["n_trials"] == 3 and tj["seed"] == 0 and len(tj["trials"]) == 3
    assert tj["sampler"] == "TPE"
    mses = [t["val_mse"] for t in tj["trials"]]
    assert all(np.isfinite(mses))
    best = tj["best"]
    assert best["val_mse"] == min(mses)
    assert best["params"] == tj["trials"][best["number"]]["params"]
    for t in tj["trials"]:
        assert {"hidden", "learning_rate", "batch_size", "alpha"} <= set(t["params"])
        assert 1 <= len(t["params"]["hidden"]) <= 2 and all(4 <= w <= 8 for w in t["params"]["hidden"])
        assert t["epochs"] >= 1
    # 저장된 모델 = 최적 설정으로 학습한 모델
    sur = load_surrogate(p)
    assert sur.training["hidden"] == best["params"]["hidden"]
    assert sur.training["learning_rate"] == best["params"]["learning_rate"]
    assert sur.training["batch_size"] == best["params"]["batch_size"]
    assert sur.training["alpha"] == best["params"]["alpha"]
    ds = load_dataset(small_dataset)
    X, Y, _ = ds.part("val")
    mse = float(np.mean((sur.predict(X)[:, 1:] - Y[:, 1:]) ** 2))
    assert mse == pytest.approx(best["val_mse"], rel=1e-9)
    assert (p / "model.joblib").is_file() and (p / "meta.json").is_file()
    assert not list(tmp_path.glob("*.partial"))


def test_with_report_writes_report_dir(small_dataset, tmp_path):
    p = tu.tune_and_save(small_dataset, tmp_path, "t2", report=True, **{**KW, "n_trials": 2})
    assert (p / "report" / "report.md").is_file() and (p / "tuning.json").is_file()


def test_search_never_touches_test_split(small_dataset):
    ds = load_dataset(small_dataset)
    d2 = copy.deepcopy(ds)
    m = d2.split == 2
    assert m.any()
    d2.X[m] = np.nan
    d2.Y[m] = np.nan
    d2.aux[m] = np.nan
    sur, study = tu.tune(d2, **KW)
    assert len(study["trials"]) == 3 and np.isfinite(study["best"]["val_mse"])
    # 테스트 세트를 NaN으로 바꾸지 않은 경우와 같은 결과
    _, study0 = tu.tune(ds, **KW)
    np.testing.assert_allclose([t["val_mse"] for t in study["trials"]],
                               [t["val_mse"] for t in study0["trials"]], rtol=1e-6)


def test_same_seed_same_trials_and_seed_changes_them(small_dataset):
    ds = load_dataset(small_dataset)
    _, a = tu.tune(ds, **KW)
    _, b = tu.tune(ds, **KW)
    assert [t["params"] for t in a["trials"]] == [t["params"] for t in b["trials"]]
    _, c = tu.tune(ds, **{**KW, "seed": 1})
    assert [t["params"] for t in a["trials"]] != [t["params"] for t in c["trials"]]


def test_default_space_is_research_r7():
    s = tu.DEFAULT_SPACE
    assert s["n_layers"] == (3, 4) and s["width"] == (64, 256)
    assert s["lr"] == (1e-4, 3e-3) and tuple(s["batch"]) == (64, 128, 256) and s["alpha"] == (1e-6, 1e-2)


def test_cli_exit_codes(small_dataset, tmp_path):
    assert tu.main(["--help"]) == 0
    assert tu.main(["--trials", "0", "--dataset", str(small_dataset), "--out", str(tmp_path)]) == 1
    assert tu.main(["--bogus"]) == 1
    assert tu.main(["--dataset", str(tmp_path / "없음"), "--out", str(tmp_path)]) == 1
    assert list(tmp_path.iterdir()) == []


def test_cli_existing_name_exit_2(small_dataset, tmp_path, monkeypatch):
    monkeypatch.setattr(tu, "DEFAULT_SPACE", SPACE)
    args = ["--dataset", str(small_dataset), "--out", str(tmp_path), "--name", "t3", "--trials", "1",
            "--no-report"]
    monkeypatch.setattr(tu, "DEFAULT_MAX_EPOCHS", 3)
    assert tu.main(args) == 0
    assert (tmp_path / "t3" / "tuning.json").is_file()
    assert tu.main(args) == 2
    assert tu.main([*args, "--overwrite"]) == 0
