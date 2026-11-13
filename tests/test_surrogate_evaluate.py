"""surrogate/evaluate.py 테스트 (specs/002 T006, research R9)."""
import json

import numpy as np
import pytest
from sklearn.metrics import r2_score

from data.io import load_dataset
from surrogate import Surrogate
from surrogate import evaluate as ev

CFG = dict(hidden=(16, 16), learning_rate=1e-3, batch_size=32, alpha=1e-4, max_epochs=20, patience=6, seed=0)


@pytest.fixture(scope="module")
def ds(small_dataset):
    return load_dataset(small_dataset)


@pytest.fixture(scope="module")
def trained(ds, small_dataset):
    return Surrogate(**CFG).fit(ds, dataset_path=str(small_dataset))


@pytest.fixture(scope="module")
def metrics(trained, ds):
    return ev.evaluate_model(trained, ds)


def _direct(trained, ds):
    X, Y, aux = ds.part("test")
    return X, Y, aux, trained.predict(X)


# ---------- ① 지표 ----------

def test_metrics_equal_direct_computation(trained, ds, metrics):
    X, Y, aux, P = _direct(trained, ds)
    r2 = 1.0 - np.sum((Y - P) ** 2) / np.sum((Y - Y.mean()) ** 2)  # 곡선 전체(모든 시점)를 한 덩어리로
    assert metrics["test_r2"] == pytest.approx(r2, rel=1e-12)
    assert metrics["test_r2"] == pytest.approx(r2_score(Y.ravel(), P.ravel()), rel=1e-12)
    assert metrics["test_rmse"] == pytest.approx(np.sqrt(np.mean((Y - P) ** 2)), rel=1e-12)
    d = np.abs(Y[:, -1] - P[:, -1])
    assert metrics["ratio365_mae"] == pytest.approx(d.mean(), rel=1e-12)
    assert metrics["ratio365_max"] == pytest.approx(d.max(), rel=1e-12)
    assert metrics["n_test"] == len(Y)
    assert ev.r2_curves(Y, P) == pytest.approx(r2, rel=1e-12)


def test_near_depletion_mae_matches_direct(trained, ds, metrics):
    X, Y, aux, P = _direct(trained, ds)
    names = list(ds.aux_names)
    te = aux[:, names.index("t_empty")]
    errs = []
    for i in range(len(Y)):
        if np.isfinite(te[i]):
            sel = np.abs(ds.t - te[i]) <= 10.0
            errs.extend(np.abs(Y[i, sel] - P[i, sel]).tolist())
    if errs:
        assert metrics["near_depletion_mae"] == pytest.approx(np.mean(errs), rel=1e-12)
    else:
        assert metrics["near_depletion_mae"] is None


def test_violation_counts_and_speed_fields(metrics):
    assert metrics["monotonic_violations"] == 0
    assert metrics["range_violations"] == 0
    assert metrics["speedup"] > 0 and np.isfinite(metrics["speedup"])
    assert metrics["speed"]["n_batch"] >= 1 and metrics["speed"]["n_ode"] >= 1


def test_violations_are_counted(trained, ds, monkeypatch):
    X, Y, aux, P = _direct(trained, ds)
    bad = P.copy()
    bad[0, 50] = 1.2          # 범위 밖
    bad[1, 60] = bad[1, 59] + 0.1   # 증가
    monkeypatch.setattr(trained, "predict", lambda X_: bad[: len(X_)] if len(X_) == len(bad) else P[: len(X_)])
    m = ev.evaluate_model(trained, ds)
    assert m["range_violations"] >= 1 and m["monotonic_violations"] >= 1
    assert m["sc_pass"]["SC-004"] is False


# ---------- ② SC 판정 ----------

OK = dict(test_r2=0.995, ratio365_mae=0.003, ratio365_max=0.02, speedup=500.0,
          monotonic_violations=0, range_violations=0)


@pytest.mark.parametrize("change,key,expected", [
    ({}, "SC-001", True), ({"test_r2": 0.99}, "SC-001", True), ({"test_r2": 0.98999}, "SC-001", False),
    ({}, "SC-002", True), ({"ratio365_mae": 0.005}, "SC-002", True),
    ({"ratio365_mae": 0.0050001}, "SC-002", False), ({"ratio365_max": 0.03}, "SC-002", True),
    ({"ratio365_max": 0.030001}, "SC-002", False),
    ({}, "SC-003", True), ({"speedup": 100.0}, "SC-003", True), ({"speedup": 99.9}, "SC-003", False),
    ({}, "SC-004", True), ({"monotonic_violations": 1}, "SC-004", False),
    ({"range_violations": 1}, "SC-004", False),
])
def test_sc_pass_boundaries(change, key, expected):
    res = ev.sc_pass({**OK, **change})
    assert set(res) == {"SC-001", "SC-002", "SC-003", "SC-004"}
    assert res[key] is expected


def test_sc_pass_criteria_are_independent():
    res = ev.sc_pass({**OK, "ratio365_max": 0.05})  # 평균은 통과, 최대는 실패 -> SC-002만 실패
    assert res == {"SC-001": True, "SC-002": False, "SC-003": True, "SC-004": True}


# ---------- ③ 보고서 파일 ----------

def test_report_files_and_top_lines(trained, ds, metrics, tmp_path):
    out = tmp_path / "report"
    ev.write_report(trained, ds, metrics, out)
    for f in ("report.md", "metrics.json", "loss_history.png", "worst_curves.png",
              "error_by_input.png", "cost_error.png"):
        assert (out / f).is_file() and (out / f).stat().st_size > 0, f
    for f in out.glob("*.png"):
        assert f.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    md = (out / "report.md").read_text(encoding="utf-8")
    first = md.splitlines()[0]
    for sc in ("SC-001", "SC-002", "SC-003", "SC-004"):
        assert sc in first                                   # 맨 위에 통과 여부
        assert ("PASS" in first) or ("FAIL" in first)
    # 상세 절보다 SC 표가 먼저 나온다
    sections = [i for i, ln in enumerate(md.splitlines()) if ln.startswith("## ")]
    table_rows = [i for i, ln in enumerate(md.splitlines()) if ln.startswith("| SC-")]
    assert len(table_rows) == 4 and max(table_rows) < sections[0]
    saved = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert saved["test_r2"] == pytest.approx(metrics["test_r2"])
    assert saved["sc_pass"] == metrics["sc_pass"]


def test_report_top_line_reflects_failure(trained, ds, metrics, tmp_path):
    bad = {**metrics, "ratio365_max": 0.5, "sc_pass": ev.sc_pass({**metrics, "ratio365_max": 0.5})}
    ev.write_report(trained, ds, bad, tmp_path / "r")
    first = (tmp_path / "r" / "report.md").read_text(encoding="utf-8").splitlines()[0]
    assert "SC-002 FAIL" in first


# ---------- ④ 오차 상위 12개 ----------

def test_worst_12_equals_manual_sort(trained, ds, metrics):
    X, Y, aux, P = _direct(trained, ds)
    err = np.abs(Y[:, -1] - P[:, -1])
    order = np.argsort(-err, kind="stable")[:12]
    ids = ds.sample_id[ds.split == 2][order]
    got = metrics["worst"]
    assert len(got) == 12
    assert [w["sample_id"] for w in got] == [int(i) for i in ids]
    assert [w["error"] for w in got] == pytest.approx(err[order].tolist(), rel=1e-12)
    assert set(got[0]["inputs"]) == set(ds.input_names)
    errs = [w["error"] for w in got]
    assert errs == sorted(errs, reverse=True)


# ---------- ⑤ 비용 환산 오차 ----------

def test_cost_error_is_price_times_m0_times_abs_delta(trained, ds, metrics):
    X, Y, aux, P = _direct(trained, ds)
    m0 = aux[:, list(ds.aux_names).index("m0")]
    direct = 5.0 * m0 * np.abs(Y[:, -1] - P[:, -1])
    np.testing.assert_allclose(ev.cost_error_usd(m0, Y[:, -1] - P[:, -1]), direct, rtol=1e-14)
    ce = metrics["cost_error"]
    assert ce["p_h2_usd_per_kg"] == 5.0
    assert ce["max"] == pytest.approx(direct.max(), rel=1e-12)
    assert ce["mean"] == pytest.approx(direct.mean(), rel=1e-12)
    assert sum(b["n"] for b in ce["bins"]) == len(direct)
    assert max(b["max"] for b in ce["bins"]) == pytest.approx(direct.max(), rel=1e-12)
    # m0 구간이 겹치지 않고 오름차순
    los = [b["m0_lo"] for b in ce["bins"]]
    assert los == sorted(los)


# ---------- CLI ----------

def test_cli_rebuilds_report(trained, tmp_path):
    p = trained.save(tmp_path / "mm")
    assert ev.main([str(p)]) == 0
    assert (p / "report" / "report.md").is_file() and (p / "report" / "metrics.json").is_file()
    meta = json.loads((p / "meta.json").read_text(encoding="utf-8"))
    assert "SC-001" in meta["metrics"]["sc_pass"]
    assert ev.main([str(tmp_path / "없는모델")]) == 1
    assert ev.main([]) == 1
