"""surrogate/model.py 테스트 (specs/002 T004, research R3~R6, contracts/model-format.md)."""
import json
import shutil

import numpy as np
import pytest

from data.io import load_dataset
from surrogate import OutOfRangeError, Surrogate, load_surrogate

CFG = dict(hidden=(16, 16), learning_rate=1e-3, batch_size=32, alpha=1e-4, max_epochs=30, patience=8, seed=0)


@pytest.fixture(scope="module")
def ds(small_dataset):
    return load_dataset(small_dataset)


@pytest.fixture(scope="module")
def trained(ds, small_dataset):
    return Surrogate(**CFG).fit(ds, dataset_path=str(small_dataset))


def _val_mse(sur, ds):
    X, Y, _ = ds.part("val")
    P = sur.predict(X)
    return float(np.mean((P[:, 1:] - Y[:, 1:]) ** 2))


def _test_mse(sur, ds):
    X, Y, _ = ds.part("test")
    return float(np.mean((sur.predict(X)[:, 1:] - Y[:, 1:]) ** 2))


# ---------- ① 출력 보장 ----------

def _assert_valid_curves(Y, n):
    assert Y.shape == (n, 100)
    assert np.all(Y[:, 0] == 1.0)
    assert np.all((Y >= 0.0) & (Y <= 1.0))
    assert np.all(np.diff(Y, axis=1) <= 0.0)


def test_predict_shape_range_monotone(trained, ds):
    X, _, _ = ds.part("test")
    _assert_valid_curves(trained.predict(X), len(X))
    np.testing.assert_array_equal(trained.t, ds.t)
    assert trained.predict_one(**dict(zip(ds.input_names, X[0]))).shape == (100,)


def test_postprocess_fixes_out_of_range_and_increasing_mlp_output(trained, ds, monkeypatch):
    X, _, _ = ds.part("test")
    n = len(X)
    rng = np.random.default_rng(0)
    raw = rng.normal(0.5, 2.0, size=(n, 99))   # 범위 밖 값 다수
    raw[0] = np.linspace(0.1, 0.9, 99)          # 증가하는 곡선
    raw[1] = -0.3                               # 전부 음수
    raw[2] = 1.7                                # 전부 1 초과
    assert (raw < 0).any() and (raw > 1).any() and np.any(np.diff(raw[0]) > 0)
    monkeypatch.setattr(trained.mlp, "predict", lambda S: raw[: len(S)])
    Y = trained.predict(X)
    _assert_valid_curves(Y, n)
    np.testing.assert_array_equal(Y[1], np.r_[1.0, np.zeros(99)])
    np.testing.assert_array_equal(Y[2], np.ones(100))
    assert Y[0, 1] == pytest.approx(0.1) and Y[0, -1] == pytest.approx(0.1)  # 누적 최솟값


# ---------- ② 범위 검사 ----------

def test_out_of_range_error_for_every_input(trained, ds):
    base = ds.X[0].copy()
    for j, nm in enumerate(ds.input_names):
        lo, hi = float(ds.input_lo[j]), float(ds.input_hi[j])
        for bad in (lo - 0.01 * (hi - lo), hi + 0.01 * (hi - lo)):
            x = base.copy()
            x[j] = bad
            with pytest.raises(OutOfRangeError) as ei:
                trained.predict(x[None, :])
            e = ei.value
            assert isinstance(e, ValueError)
            assert (e.name, e.value, e.lo, e.hi) == (nm, bad, lo, hi)
            with pytest.raises(OutOfRangeError):
                trained.check_range(x[None, :])
            with pytest.raises(OutOfRangeError):
                trained.ratio365(x[None, :])


def test_nan_input_rejected(trained, ds):
    x = ds.X[0].copy()
    x[2] = np.nan
    with pytest.raises(OutOfRangeError):
        trained.predict(x[None, :])


def test_non_integer_N_is_allowed(trained, ds):
    x = ds.X[0].copy()
    x[ds.input_names.index("N")] = 57.5
    trained.check_range(x[None, :])
    _assert_valid_curves(trained.predict(x[None, :]), 1)
    y = trained.predict_one(**dict(zip(ds.input_names, x)))
    assert y.shape == (100,)


def test_range_endpoints_are_accepted(trained, ds):
    trained.check_range(ds.input_lo[None, :])
    trained.check_range(ds.input_hi[None, :])
    trained.check_range(ds.X)  # 학습 데이터 전체가 범위 안


def test_train_range_exposed(trained, ds):
    r = trained.train_range
    assert r["names"] == list(ds.input_names)
    np.testing.assert_array_equal(r["lo"], ds.input_lo)
    np.testing.assert_array_equal(r["hi"], ds.input_hi)


# ---------- ③ 조기 종료와 테스트 세트 ----------

def test_early_stopping_uses_validation_set_and_best_weights(ds):
    sur = Surrogate(hidden=(16, 16), learning_rate=1e-2, batch_size=32, alpha=1e-4,
                    max_epochs=200, patience=5, seed=0).fit(ds)
    val = sur.history["val_mse"]
    assert len(sur.history["train_mse"]) == len(val)
    assert sur.best_epoch == int(np.argmin(val)) + 1            # 1부터 세는 epoch 번호
    assert sur.best_epoch < len(val)                              # 마지막 epoch가 최선이 아니었다
    # 조기 종료: 최선 이후 patience epoch만큼만 더 돌았다 (최대 epoch에 닿지 않았다)
    assert len(val) == sur.best_epoch + 5
    # 최종 모델은 가장 좋았던 epoch의 가중치다 (마지막 epoch가 아님)
    assert _val_mse(sur, ds) == pytest.approx(min(val), rel=1e-9)
    assert _val_mse(sur, ds) < val[-1]


def test_training_never_touches_test_split(ds, trained):
    import copy
    d2 = copy.deepcopy(ds)
    m = d2.split == 2
    assert m.any()
    d2.X[m] = np.nan
    d2.Y[m] = np.nan
    d2.aux[m] = np.nan
    sur = Surrogate(**CFG).fit(d2)
    np.testing.assert_allclose(sur.history["val_mse"], trained.history["val_mse"], rtol=1e-6)
    assert sur.best_epoch == trained.best_epoch


def test_fit_rejects_empty_validation(ds):
    import copy
    d2 = copy.deepcopy(ds)
    d2.split[d2.split == 1] = 0
    with pytest.raises(ValueError):
        Surrogate(**CFG).fit(d2)


# ---------- ④ 저장·불러오기 ----------

def test_save_load_roundtrip(trained, ds, tmp_path):
    X, _, _ = ds.part("test")
    p = trained.save(tmp_path / "m1")
    assert p == tmp_path / "m1"
    assert (p / "model.joblib").is_file() and (p / "meta.json").is_file()
    assert not list(tmp_path.glob("*.partial"))
    loaded = load_surrogate(p)
    np.testing.assert_allclose(loaded.predict(X), trained.predict(X), rtol=0, atol=1e-12)
    np.testing.assert_array_equal(loaded.t, trained.t)
    assert loaded.train_range == trained.train_range
    assert loaded.best_epoch == trained.best_epoch
    assert loaded.physics_matches() is True
    meta = json.loads((p / "meta.json").read_text(encoding="utf-8"))
    assert meta["format_version"] == 1 and meta["name"] == "m1"


def test_load_rejects_partial_and_unknown_version(trained, tmp_path):
    p = trained.save(tmp_path / "m2")
    for name in ("m2x.partial", "m2y.PARTIAL"):
        d = tmp_path / name
        shutil.copytree(p, d)
        with pytest.raises(ValueError):
            load_surrogate(d)
    bad = tmp_path / "m2bad"
    shutil.copytree(p, bad)
    meta = json.loads((bad / "meta.json").read_text(encoding="utf-8"))
    meta["format_version"] = 99
    (bad / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError):
        load_surrogate(bad)


def test_save_existing_and_name_rules(trained, tmp_path):
    from surrogate.model import ModelExistsError
    p = trained.save(tmp_path / "m3")
    with pytest.raises(ModelExistsError):
        trained.save(tmp_path / "m3")
    assert (p / "model.joblib").is_file()
    trained.save(tmp_path / "m3", overwrite=True)
    assert not list(tmp_path.glob("m3.*"))                      # .partial/.old 잔여물 없음
    for bad in ("a b", "x.partial", "x.OLD", "..", "a..b"):
        with pytest.raises(ValueError):
            trained.save(tmp_path / bad)
    # 이미 있는 .partial은 지우지 않고 멈춘다
    (tmp_path / "m4.partial").mkdir()
    with pytest.raises(ModelExistsError):
        trained.save(tmp_path / "m4")
    assert (tmp_path / "m4.partial").is_dir()


def test_failed_save_leaves_nothing_and_keeps_old_model(trained, tmp_path):
    p = trained.save(tmp_path / "m5")
    before = (p / "model.joblib").read_bytes()

    def boom(partial_dir):
        assert partial_dir.name == "m5.partial" and (partial_dir / "model.joblib").is_file()
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        trained.save(tmp_path / "m5", overwrite=True, write_extra=boom)
    assert sorted(x.name for x in tmp_path.iterdir()) == ["m5"]
    assert (p / "model.joblib").read_bytes() == before


def test_meta_has_no_economic_keys(trained, tmp_path):
    p = trained.save(tmp_path / "m6")
    text = (p / "meta.json").read_text(encoding="utf-8").lower()
    for word in ("cost", "c_layer", "c_fixed", "p_h2", "price", "discount"):
        assert word not in text
    assert "log10_k" in text


# ---------- ⑤ 재현성 ----------

def test_same_seed_same_result_and_seed_matters(ds, trained):
    again = Surrogate(**CFG).fit(ds)
    assert _test_mse(again, ds) == pytest.approx(_test_mse(trained, ds), rel=1e-6)
    other = Surrogate(**{**CFG, "seed": 1}).fit(ds)
    assert not np.allclose(other.history["val_mse"][:5], trained.history["val_mse"][:5], rtol=1e-3)


# ---------- ⑥ ratio365 ----------

def test_ratio365_equals_last_column(trained, ds):
    X, _, _ = ds.part("test")
    np.testing.assert_array_equal(trained.ratio365(X), trained.predict(X)[:, -1])


def test_physics_matches_detects_change(trained):
    import copy
    s = copy.copy(trained)
    s.dataset_info = {**trained.dataset_info, "physics": {"version": "0.1.0", "sha256": "0" * 64}}
    assert s.physics_matches() is False
