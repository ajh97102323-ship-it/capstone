"""optimize/analysis.py 테스트: 민감도(T007), 잔량 목표 제약·Pareto(T011). ODE를 감싼 ode_sur fixture를 쓴다."""
import json
from dataclasses import replace

import numpy as np
import pytest

from physics import CostParams, DesignParams, analytic_optimal_layers

from optimize.analysis import pareto, sensitivity
from optimize.layers import optimize_layers, verify_with_ode
from optimize.problem import Problem


def _design(**kw):
    d = {k: v for k, v in vars(DesignParams()).items() if k != "Th"}
    d.update(kw)
    return d


PH2 = np.linspace(2.0, 15.0, 14)
CLAYER = np.linspace(5.0, 30.0, 11)


@pytest.fixture(scope="module")
def prob():
    return Problem(_design())


@pytest.fixture(scope="module")
def sens_ph2(ode_sur, prob):
    return sensitivity(ode_sur, prob, "p_h2", PH2, ode_every=3)


@pytest.fixture(scope="module")
def sens_cl(ode_sur, prob):
    return sensitivity(ode_sur, prob, "c_layer", CLAYER, ode_every=3)


# ① 방향
def test_ph2_nondecreasing(sens_ph2):
    n = sens_ph2.n_sur
    assert np.all(np.diff(n) >= 0) and n[0] < n[-1]
    assert sens_ph2.monotone_ok is True
    assert sens_ph2.param == "p_h2" and np.allclose(sens_ph2.values, PH2)


def test_clayer_nonincreasing(sens_cl):
    n = sens_cl.n_sur
    assert np.all(np.diff(n) <= 0) and n[0] > n[-1]
    assert sens_cl.monotone_ok is True


# ② 근사식
def test_analytic_matches_each_point(sens_ph2, sens_cl, prob):
    for sens, name in ((sens_ph2, "p_h2"), (sens_cl, "c_layer")):
        for v, na in zip(sens.values, sens.n_analytic):
            cost = replace(prob.cost, **{name: float(v)})
            assert na == pytest.approx(analytic_optimal_layers(prob.design_params(), cost))
    assert np.sign(sens_ph2.n_analytic[-1] - sens_ph2.n_analytic[0]) == 1
    assert np.sign(sens_cl.n_analytic[-1] - sens_cl.n_analytic[0]) == -1
    assert sens_ph2.matches_analytic is True and sens_cl.matches_analytic is True


# ③ ode_every
def test_ode_every(sens_ph2, ode_sur, prob):
    n_ode = np.asarray(sens_ph2.n_ode, dtype=float)
    idx = np.arange(len(PH2))
    assert np.all(np.isfinite(n_ode[idx % 3 == 0])) and np.all(np.isnan(n_ode[idx % 3 != 0]))
    # 계산한 점의 값은 해당 점에서의 ODE 전 범위 스캔 최적 N과 같다 (ode_sur이므로 대리모델 최적 N과도 같다)
    assert np.array_equal(n_ode[::3], np.asarray(sens_ph2.n_sur, dtype=float)[::3])


def test_ode_every_one_and_to_dict(ode_sur, prob):
    s = sensitivity(ode_sur, prob, "life_years", [10.0, 20.0, 40.0], ode_every=1)
    assert np.all(np.isfinite(np.asarray(s.n_ode, dtype=float)))
    assert s.monotone_ok is True  # 수명이 길수록 연환산 MLI 비용 감소 -> N 증가
    json.dumps(s.to_dict())


def test_discount_direction(ode_sur, prob):
    s = sensitivity(ode_sur, prob, "discount", [0.0, 0.05, 0.10], ode_every=2)
    assert np.all(np.diff(s.n_sur) <= 0) and s.n_sur[0] > s.n_sur[-1] and s.monotone_ok is True


# ④ 잘못된 이름
@pytest.mark.parametrize("name", ["foo", "N", "LD"])
def test_bad_param_name(ode_sur, prob, name):
    with pytest.raises(ValueError):
        sensitivity(ode_sur, prob, name, [1.0, 2.0])


@pytest.mark.parametrize("name", ["Nbar", "eps"])
def test_unpriced_param_rejected_like_check_variables(ode_sur, prob, name):
    with pytest.raises(ValueError, match="비용"):
        sensitivity(ode_sur, prob, name, [1.0, 2.0])


# ---------------- T011: 잔량 목표 제약 ----------------

def _ratio_at(res, day):
    return np.array([np.interp(day, res.t, c) for c in res.curves])


def test_residual_active(ode_sur, prob):
    free = optimize_layers(ode_sur, prob)
    r = float(_ratio_at(free, 180.0)[free.N == free.n_opt][0]) + 0.02
    res = optimize_layers(ode_sur, replace(prob, residual=(180.0, r)))
    assert res.n_opt is not None and res.n_opt > free.n_opt
    assert res.n_unconstrained == free.n_opt
    assert any(w.startswith("RESIDUAL_ACTIVE") for w in res.warnings)
    assert _ratio_at(res, 180.0)[res.N == res.n_opt][0] >= r
    assert np.array_equal(res.residual_ok, _ratio_at(res, 180.0) >= r)
    assert np.array_equal(res.feasible, ~res.depleted & res.residual_ok)


def test_residual_inactive_when_loose(ode_sur, prob):
    free = optimize_layers(ode_sur, prob)
    res = optimize_layers(ode_sur, replace(prob, residual=(180.0, 0.01)))
    assert res.n_opt == free.n_opt and not any(w.startswith("RESIDUAL") for w in res.warnings)


def test_residual_infeasible(ode_sur, prob):
    res = optimize_layers(ode_sur, replace(prob, residual=(180.0, 0.9999)))
    assert res.n_opt is None and res.total_opt is None
    w = [w for w in res.warnings if w.startswith("RESIDUAL_INFEASIBLE")]
    assert len(w) == 1
    closest = int(res.N[np.argmax(np.where(res.depleted, -np.inf, _ratio_at(res, 180.0)))])
    assert res.n_closest == closest and str(closest) in w[0]
    json.dumps(res.to_dict())


def test_residual_verify_runs(ode_sur, prob):
    free = optimize_layers(ode_sur, prob)
    r = float(_ratio_at(free, 180.0)[free.N == free.n_opt][0]) + 0.02
    p2 = replace(prob, residual=(180.0, r))
    ver = verify_with_ode(p2, optimize_layers(ode_sur, p2))
    assert ver.n_recommended is not None and ver.n_recommended >= free.n_opt


# ---------------- T011: Pareto ----------------

def test_pareto(ode_sur, prob):
    res = optimize_layers(ode_sur, prob)
    par = pareto(ode_sur, prob)
    f = res.feasible
    assert np.array_equal(par.N, res.N[f])
    assert np.allclose(par.capex, res.capex[f]) and np.allclose(par.m_lost, res.m_lost[f])
    # 비지배 판정을 직접 계산: 다른 점 중 capex와 m_lost가 모두 ≤이고 하나는 <인 점이 없어야 비지배
    x, y = par.capex, par.m_lost
    expect = np.array([not any((x[j] <= x[i] and y[j] <= y[i]) and (x[j] < x[i] or y[j] < y[i])
                               for j in range(len(x))) for i in range(len(x))])
    assert np.array_equal(par.pareto_mask, expect) and par.pareto_mask.any()
    assert par.n_cost_opt == res.n_opt
    assert par.pareto_mask[list(par.N).index(par.n_cost_opt)]
    json.dumps(par.to_dict())


def test_pareto_dominated_detected(ode_sur):
    """보일오프가 N에 대해 단조 감소하지 않는 설계(소진 가장자리)가 없어도, 판정식이 지배 점을 거른다:
    capex가 같고 m_lost만 큰 점을 인위적으로 넣은 입력으로 내부 판정 함수를 시험한다."""
    from optimize.analysis import nondominated
    x = np.array([1.0, 2.0, 3.0, 3.0])
    y = np.array([5.0, 3.0, 1.0, 2.0])
    assert nondominated(x, y).tolist() == [True, True, True, False]
