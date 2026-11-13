"""optimize/layers.py 테스트 (specs/003 T003). ODE를 감싼 ode_sur fixture를 쓴다."""
import json

import numpy as np
import pytest

from physics import CostParams, DesignParams, analytic_optimal_layers, cost_vs_layers

from optimize.layers import analytic_n, ode_scan, optimize_layers, verify_with_ode
from optimize.problem import DEPLETION_TOL, Problem


def _design(**kw):
    d = {k: v for k, v in vars(DesignParams()).items() if k != "Th"}
    d.update(kw)
    return d


# 일부 N이 소진되는 설계: R=0.8, fill=0.5 (N=10~40 소진, 80 이상 생존)
DEPLETED_KW = dict(R=0.8, LD=0.0, fill=0.5)
# 모든 N이 소진되는 설계: 아주 작은 탱크
ALL_DEPLETED_KW = dict(R=0.3, LD=0.0, fill=0.5, Pv0=0.1, G_sup=1e-2, G_out=1e-6, S=1e-4)


@pytest.fixture(scope="module")
def base(ode_sur):
    prob = Problem(_design())
    return prob, optimize_layers(ode_sur, prob)


# ① 격자·argmin·U자
def test_grid_argmin_and_u_shape(base):
    prob, res = base
    assert res.N.dtype.kind == "i" and res.N.tolist() == list(range(10, 121)) and len(res.N) == 111
    assert res.curves.shape == (111, 100)
    # 기본 설계는 N=10~12에서 365일 안에 소진된다(ODE 확인). 소진 후보는 제외되고 나머지에서 argmin
    assert np.array_equal(res.feasible, ~res.depleted) and res.depleted[:3].all() and res.feasible[3:].all()
    f = res.feasible
    assert res.n_opt == int(res.N[f][np.argmin(res.annual_total[f])])
    assert res.total_opt == pytest.approx(res.annual_total[f].min())
    assert res.annual_total[f][0] > res.total_opt and res.annual_total[-1] > res.total_opt  # U자
    assert 10 < res.n_opt < 120 and not res.depleted[res.N == res.n_opt][0]
    assert [w.split(":")[0] for w in res.warnings] == ["DEPLETED_EXCLUDED"] and res.elapsed_s >= 0


# ② 비용 분해 단조성
def test_cost_components_monotone(base):
    _, res = base
    f = res.feasible  # 소진 후보는 손실이 m0에서 잘려 보일오프 비용이 과소평가되므로 제외하고 본다
    assert np.all(np.diff(res.annual_mli) > 0)
    assert np.all(np.diff(res.annual_boiloff[f]) < 0)
    assert np.allclose(res.annual_total, res.annual_mli + res.annual_boiloff)
    assert np.all(np.diff(res.capex) > 0)


# ③ 평평한 구간
def test_flat_range(base):
    _, res = base
    ok = res.N[res.feasible & (res.annual_total <= res.total_opt * 1.01)]
    assert res.flat == (int(ok.min()), int(ok.max()))
    assert res.flat[0] <= res.n_opt <= res.flat[1]
    assert res.flat[1] > res.flat[0]


# ④ 소진 제외
def test_depleted_candidates_excluded(ode_sur):
    prob = Problem(_design(**DEPLETED_KW))
    res = optimize_layers(ode_sur, prob)
    dep = res.ratio365 < DEPLETION_TOL
    assert dep.any() and (~dep).any()
    assert np.array_equal(res.depleted, dep)
    assert not res.feasible[dep].any() and res.feasible[~dep].all()
    assert any(w.startswith("DEPLETED_EXCLUDED") for w in res.warnings)
    assert not dep[res.N == res.n_opt][0]
    assert res.n_opt == int(res.N[res.feasible][np.argmin(res.annual_total[res.feasible])])
    in_flat = (res.N >= res.flat[0]) & (res.N <= res.flat[1])
    assert not dep[in_flat].any()


def test_all_depleted_no_feasible(ode_sur):
    prob = Problem(_design(**ALL_DEPLETED_KW))
    res = optimize_layers(ode_sur, prob)
    assert res.depleted.all() and not res.feasible.any()
    assert res.n_opt is None and res.total_opt is None and res.flat is None
    assert any(w.startswith("NO_FEASIBLE") for w in res.warnings)
    assert any(w.startswith("DEPLETED_EXCLUDED") for w in res.warnings)
    v = verify_with_ode(prob, res)  # 실행 가능 후보가 없어도 깨지지 않는다
    assert v.n_recommended is None and v.dN is None and v.rel_cost_err is None
    json.dumps(v.to_dict())


# ⑤ 경계 최적
def test_boundary_high_and_low(ode_sur):
    hi = optimize_layers(ode_sur, Problem(_design(), CostParams(p_h2=1e4)))
    assert hi.n_opt == 120 and any(w.startswith("BOUNDARY_HIGH") for w in hi.warnings)
    lo = optimize_layers(ode_sur, Problem(_design(R=2.5), CostParams(p_h2=1e-3)))  # R=2.5는 N=10도 생존
    assert lo.n_opt == 10 and any(w.startswith("BOUNDARY_LOW") for w in lo.warnings)
    mid = optimize_layers(ode_sur, Problem(_design()))
    assert not any(w.startswith("BOUNDARY") for w in mid.warnings)


# ⑥ ODE 재검증
def test_verify_with_ode(base):
    prob, res = base
    v = verify_with_ode(prob, res)
    assert 3 <= len(v.candidates) <= 5 and len(v.candidates) == len(v.candidate_totals_ode)
    order = np.argsort(res.annual_total, kind="stable")[: len(v.candidates)]  # 대리모델 총비용 순 상위
    assert v.candidates == [int(res.N[i]) for i in order]
    assert v.n_recommended == v.candidates[int(np.argmin(v.candidate_totals_ode))]
    ref = cost_vs_layers(prob.design_params(), prob.cost, range(10, 121))
    for k in ("N", "annual_mli", "annual_boiloff", "annual_total", "m_lost", "depleted"):
        assert np.array_equal(v.scan[k], ref[k]), k
    for n, c in zip(v.candidates, v.candidate_totals_ode):
        assert c == pytest.approx(ref["annual_total"][n - 10], rel=1e-12)
    i = int(np.argmin(ref["annual_total"]))
    assert v.n_ode == int(ref["N"][i]) and v.total_ode == pytest.approx(ref["annual_total"][i])
    assert v.total_ode_at_sur == pytest.approx(ref["annual_total"][res.n_opt - 10])
    assert v.rel_cost_err == pytest.approx((v.total_ode_at_sur - v.total_ode) / v.total_ode)
    assert v.dN == res.n_opt - v.n_ode
    # ODE를 감싼 대리모델이므로 완전히 일치
    assert v.dN == 0 and v.rel_cost_err == 0
    assert v.n_recommended == v.n_ode


def test_verify_top_k(base):
    prob, res = base
    assert len(verify_with_ode(prob, res, top_k=3).candidates) == 3


def test_ode_scan_matches_physics(base):
    prob, _ = base
    s = ode_scan(prob)
    ref = cost_vs_layers(prob.design_params(), prob.cost, range(10, 121))
    assert set(s) == set(ref)
    for k in ref:
        assert np.array_equal(s[k], ref[k]), k
    sub = ode_scan(Problem(_design(), n_range=(20, 30)))
    assert sub["N"].tolist() == list(range(20, 31))


# ⑦ 근사식
def test_analytic_n(base):
    prob, res = base
    v = verify_with_ode(prob, res)
    assert analytic_n(prob) == analytic_optimal_layers(prob.design_params(), prob.cost)
    assert abs(analytic_n(prob) - v.n_ode) / v.n_ode <= 0.12
    assert v.n_analytic == analytic_n(prob)


# ⑧ optimize_layers는 ODE를 부르지 않는다
class _FakeSur:
    """ODE 없이 곡선을 만드는 일반 대리모델 대역 (1/N 형태 손실)."""
    input_names = ["N", "Nbar", "eps", "G_sup", "Pv0", "G_out", "S", "R", "LD", "fill"]
    t = np.linspace(0.0, 365.0, 100)

    @property
    def train_range(self):
        lo = [10, 10, 0.02, 1e-4, 1e-4, 1e-9, 1e-4, 0.3, 0, 0.5]
        hi = [120, 30, 0.06, 1e-2, 0.1, 1e-6, 1e-2, 2.5, 3, 0.95]
        return {"names": self.input_names, "lo": lo, "hi": hi}

    def check_range(self, X):
        pass

    def predict(self, X):
        X = np.asarray(X)
        assert len(X) > 0
        loss = 1.0 / (1.0 + 0.02 * X[:, :1])
        return 1.0 - 0.6 * loss * (self.t[None, :] / 365.0)


def test_optimize_layers_does_not_call_ode(monkeypatch):
    import physics.model as pm

    def boom(*a, **k):
        raise AssertionError("ODE 호출 금지")
    monkeypatch.setattr(pm, "solve_ivp", boom)
    res = optimize_layers(_FakeSur(), Problem(_design()))
    assert res.n_opt is not None and res.feasible.all()
    assert res.n_opt == int(res.N[np.argmin(res.annual_total)])


# ⑨ 직렬화
def test_to_dict_json_serializable(base):
    prob, res = base
    back = json.loads(json.dumps(res.to_dict()))
    assert back["n_opt"] == res.n_opt and len(back["N"]) == 111
    json.dumps(verify_with_ode(prob, res).to_dict())


def test_input_out_of_range_rejected(ode_sur):
    from surrogate import OutOfRangeError
    with pytest.raises(OutOfRangeError):
        optimize_layers(ode_sur, Problem(_design(R=9.0)))


def test_residual_not_silently_ignored(ode_sur):
    """T012 구현 후: 잔량 제약이 실제로 후보를 거른다 (자세한 시험은 test_optimize_analysis.py)."""
    free = optimize_layers(ode_sur, Problem(_design()))
    res = optimize_layers(ode_sur, Problem(_design(), residual=(180, 0.9999)))
    assert free.n_opt is not None and res.n_opt is None and not res.residual_ok.all()


# ---------------- 반려 보완: 비정상 대리모델 출력, inf 경제 변수 ----------------

class _NaNSur:
    """ode_sur를 감싸 지정한 N 행의 출력을 NaN/inf로 바꾼다."""

    def __init__(self, inner, bad_n, value=np.nan, all_bad=False):
        self._i, self._bad, self._v, self._all = inner, set(bad_n), value, all_bad
        self.input_names, self.t, self.train_range = inner.input_names, inner.t, inner.train_range
        self.check_range = inner.check_range

    def predict(self, X):
        Y = np.array(self._i.predict(X), dtype=float)
        j = self.input_names.index("N")
        for k, row in enumerate(np.asarray(X)):
            if self._all or int(row[j]) in self._bad:
                Y[k, 50:] = self._v
        return Y


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_nonfinite_candidates_infeasible(ode_sur, value):
    prob = Problem(_design())
    ref = optimize_layers(ode_sur, prob)
    bad = [ref.n_opt, ref.n_opt + 1]
    res = optimize_layers(_NaNSur(ode_sur, bad, value), prob)
    for n in bad:
        assert not res.feasible[res.N == n][0]
    assert res.n_opt is not None and res.n_opt not in bad and np.isfinite(res.total_opt)
    assert any(w.startswith("NONFINITE_EXCLUDED") for w in res.warnings)
    json.dumps(res.to_dict())
    verify_with_ode(prob, res)  # 크래시 없음


def test_all_nonfinite_no_feasible(ode_sur):
    prob = Problem(_design())
    res = optimize_layers(_NaNSur(ode_sur, [], all_bad=True), prob)
    assert res.n_opt is None and not res.feasible.any()
    assert any(w.startswith("NO_FEASIBLE") for w in res.warnings)
    json.dumps(res.to_dict())


@pytest.mark.parametrize("kw", [dict(p_h2=float("inf")), dict(c_layer=float("inf")), dict(life_years=float("inf")),
                                dict(c_fixed=float("inf")), dict(discount=float("inf")), dict(p_h2=float("nan"))])
def test_inf_nan_economics_rejected(kw):
    with pytest.raises(ValueError):
        Problem(_design(), CostParams(**kw))
