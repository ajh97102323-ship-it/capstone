"""app/logic.py 단위 테스트 (specs/004 T001·T005·T007·T009·T011). 대리모델은 ODE 래퍼(ode_sur)."""
import threading
import time

import numpy as np
import pytest

from optimize import Problem, cost_arrays, optimize_layers
from physics import BoiloffModel, CostParams, DesignParams, simulate
from physics.model import H_FG
from surrogate import OutOfRangeError

from app import logic

DESIGN_KEYS = ["N", "Nbar", "eps", "G_sup", "Pv0", "G_out", "S", "R", "LD", "fill"]


def _design(**kw):
    d = {k: getattr(DesignParams(), k) for k in DESIGN_KEYS}
    d.update(kw)
    return d


def _x(sur, d):
    return np.array([[d[k] for k in sur.input_names]])


# ---------- T001 ① input_specs ----------
def test_input_specs(ode_sur):
    specs = logic.input_specs(ode_sur)
    tr = ode_sur.train_range
    assert [s.name for s in specs] == tr["names"] == DESIGN_KEYS
    for s, lo, hi in zip(specs, tr["lo"], tr["hi"]):
        assert (s.lo, s.hi) == (lo, hi)
        assert lo <= s.default <= hi
        assert "[" in s.label and s.label.rstrip().endswith("]")
        assert s.log == (s.name in ("G_sup", "Pv0", "G_out", "S"))
        if s.log:
            assert len(s.options) == 61
            assert s.options[0] == pytest.approx(lo) and s.options[-1] == pytest.approx(hi)
            r = np.diff(np.log10(s.options))
            assert np.allclose(r, r[0])
            assert s.default in s.options
        else:
            assert s.options is None
    assert next(s for s in specs if s.name == "N").step == 1
    assert "[-]" in next(s for s in specs if s.name == "eps").label


# ---------- T001 ② ③ ④ ⑤ summarize ----------
def test_summarize_values(ode_sur):
    d, cost = _design(), CostParams()
    s = logic.summarize(ode_sur, d, cost, 100.0)
    curve = ode_sur.predict(_x(ode_sur, d))[0]
    assert np.array_equal(s.curve, curve) and np.array_equal(s.t, ode_sur.t)
    m = BoiloffModel(DesignParams(**d))
    assert s.m0 == m.m0
    assert s.Q0 == m.heat_to_liquid(0, m.m0)
    assert s.ratio_at_query == pytest.approx(np.interp(100.0, ode_sur.t, curve))
    assert s.boiloff_rate == pytest.approx(s.Q0 / H_FG / m.m0 * 86400 * 100)
    c = cost_arrays(Problem(d, cost), [d["N"]], [curve[-1]])
    assert s.annual_mli == pytest.approx(c["annual_mli"][0])
    assert s.annual_boiloff == pytest.approx(c["annual_boiloff"][0])
    assert s.annual_total == pytest.approx(c["annual_total"][0])
    assert not s.depleted and s.t_empty is None


def test_summarize_n_monotone(ode_sur):
    a = logic.summarize(ode_sur, _design(N=30), CostParams())
    b = logic.summarize(ode_sur, _design(N=90), CostParams())
    assert b.annual_boiloff < a.annual_boiloff and b.annual_mli > a.annual_mli


def test_summarize_depleted(ode_sur):
    from optimize import DEPLETION_TOL
    s = logic.summarize(ode_sur, _design(R=0.3, Pv0=0.1, N=10), CostParams())
    assert s.depleted and 0 < s.t_empty < 365
    assert np.interp(s.t_empty, s.t, s.curve) == pytest.approx(DEPLETION_TOL, abs=5e-3)


def test_summarize_out_of_range(ode_sur):
    with pytest.raises(OutOfRangeError):
        logic.summarize(ode_sur, _design(R=5.0), CostParams())


def test_load_model_errors(tmp_path):
    with pytest.raises(Exception) as e:
        logic.load_model(tmp_path / "없음")
    assert "없음" in str(e.value)
    with pytest.raises(Exception) as e:
        logic.load_model(tmp_path / "m.partial")
    assert "partial" in str(e.value)
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "meta.json").write_text("{", encoding="utf-8")
    with pytest.raises(Exception) as e:
        logic.load_model(tmp_path / "bad")
    assert "bad" in str(e.value)


# ---------- T005 optimize_view ----------
def test_optimize_view_matches_optimize_layers(ode_sur):
    d, cost = _design(), CostParams()
    v = logic.optimize_view(ode_sur, d, cost)
    r = optimize_layers(ode_sur, Problem(d, cost))
    assert v.n_opt == r.n_opt and v.flat == r.flat and v.warnings == r.warnings
    assert v.volume is None


def test_optimize_view_p_h2_monotone(ode_sur):
    n5 = logic.optimize_view(ode_sur, _design(), CostParams(p_h2=5)).n_opt
    n10 = logic.optimize_view(ode_sur, _design(), CostParams(p_h2=10)).n_opt
    assert n10 >= n5


def test_optimize_view_residual_and_volume_passed(ode_sur, monkeypatch):
    """residual은 Problem으로, volume은 optimize.optimize_volume(verify=False)로 전달한다."""
    import optimize
    seen = {}

    def fake_layers(sur, problem):
        seen["residual"] = problem.residual
        return optimize_layers(sur, Problem(problem.design, problem.cost, problem.n_range))

    def fake_volume(sur, design, cost, V, D_max=None, **kw):
        seen["vol"] = (V, D_max, kw)
        return "VOL"

    monkeypatch.setattr(logic, "optimize_layers", fake_layers)
    monkeypatch.setattr(optimize, "optimize_volume", fake_volume, raising=False)
    v = logic.optimize_view(ode_sur, _design(), CostParams(), residual=(200.0, 0.2), volume=(50.0, 4.0))
    assert seen["residual"] == (200.0, 0.2)
    assert seen["vol"][:2] == (50.0, 4.0) and seen["vol"][2].get("verify") is False
    assert v.volume == "VOL"


# ---------- T007 validate ----------
def test_validate(ode_sur):
    d, cost = _design(), CostParams()
    v = logic.validate(ode_sur, d, cost)
    _, ode = simulate(DesignParams(**d))
    assert np.allclose(v.curve_ode, ode, rtol=0, atol=1e-12)
    ai = ode_sur.predict(_x(ode_sur, d))[0]
    assert np.array_equal(v.curve_ai, ai)
    assert v.max_abs_err == pytest.approx(np.max(np.abs(ai - ode)))
    assert v.err365 == pytest.approx(ai[-1] - ode[-1])
    m0 = BoiloffModel(DesignParams(**d)).m0
    assert v.cost_diff == pytest.approx(cost.p_h2 * m0 * abs(ai[-1] - ode[-1]))
    assert v.ms_ai > 0 and v.ms_ode > 0


# ---------- T009 저장·비교 ----------
def test_saved_list(ode_sur):
    saved = []
    s = logic.summarize(ode_sur, _design(), CostParams())
    logic.add_saved(saved, "A", _design(), s)
    logic.add_saved(saved, "B", _design(N=60), s)
    assert [x["name"] for x in saved] == ["A", "B"]
    for bad in ("", "   ", "A"):
        with pytest.raises(ValueError):
            logic.add_saved(saved, bad, _design(), s)
    assert len(saved) == 2
    rows = logic.compare_table(saved)
    assert [r["이름"] for r in rows] == ["A", "B"]
    assert rows[1]["N [layer]"] == 60
    assert rows[0]["총비용 [$/yr]"] == pytest.approx(s.annual_total)
    logic.remove_saved(saved, "A")
    assert [x["name"] for x in saved] == ["B"]


# ---------- T011 동시성 ----------
def _concurrency_model(ode_sur):
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "models" / "mlp_lhs_n500_seed42_seed0_tuned"
    if p.is_dir():
        try:
            return logic.load_model(p)
        except Exception:
            pass
    return ode_sur


def test_concurrent_five_threads(ode_sur):
    sur = _concurrency_model(ode_sur)
    cost = CostParams()
    for i in range(5):  # ODE 래퍼 캐시 워밍업(첫 계산 비용 제외)
        d = _design(R=1.0 + 0.05 * i)
        logic.summarize(sur, d, cost)
        logic.optimize_view(sur, d, cost)
        logic.validate(sur, d, cost)
    worst, errs = [0.0] * 5, []

    def work(i):
        try:
            for k in range(20):
                d = _design(R=1.0 + 0.05 * i)
                t0 = time.perf_counter()
                logic.summarize(sur, d, cost)
                logic.optimize_view(sur, d, cost)
                if i == 0 and k % 5 == 0:
                    logic.validate(sur, d, cost)
                worst[i] = max(worst[i], time.perf_counter() - t0)
        except Exception as e:  # noqa: BLE001
            errs.append(e)

    ths = [threading.Thread(target=work, args=(i,)) for i in range(5)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    assert not errs, errs
    assert max(worst) < 1.0, worst
