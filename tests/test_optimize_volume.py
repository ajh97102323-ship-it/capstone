"""optimize/volume.py 테스트 (specs/003 T009). ODE를 감싼 ode_sur fixture를 쓴다.

속도를 위해 L/D 간격 0.1(31점)을 쓴다(기본 0.05는 61점)."""
import json

import numpy as np
import pytest

from physics import CapsuleTank, CostParams, DesignParams

from optimize.problem import Problem, cost_arrays
from optimize.volume import optimize_volume, radius_for_volume

V = 30.0
STEP = 0.1


def _design(**kw):
    d = {k: v for k, v in vars(DesignParams()).items() if k != "Th"}
    d.update(kw)
    return d


@pytest.fixture(scope="module")
def free(ode_sur):
    return optimize_volume(ode_sur, _design(), CostParams(), V, ld_step=STEP)


@pytest.fixture(scope="module")
def capped(ode_sur):
    return optimize_volume(ode_sur, _design(), CostParams(), V, D_max=3.0, ld_step=STEP)


# ① 반경 공식
@pytest.mark.parametrize("v", [5.0, 30.0, 80.0])
def test_radius_for_volume(v):
    ld = np.array([0.0, 0.5, 1.0, 3.0])
    R = radius_for_volume(v, ld)
    for r, l in zip(R, ld):
        assert CapsuleTank(r, 2 * r * l).V_tot == pytest.approx(v, rel=1e-9)
    assert radius_for_volume(v, 1.0) == pytest.approx(R[2])


# ② 직경 제약 없음: 구형에 가까운 쪽
def test_free_prefers_near_sphere(free):
    assert free.ld_opt <= 0.2
    assert free.ld_feasible.all() and free.total.shape == (len(free.LD), len(free.N))
    assert free.N.tolist() == list(range(10, 121))
    assert free.V == V and free.D_max is None


# ③ 직경 제약
def test_diameter_cap(capped):
    assert 2 * capped.R_opt <= 3.0 + 1e-12
    ld_min_ok = capped.LD[capped.ld_feasible].min()
    assert capped.ld_opt <= ld_min_ok + 0.3 + 1e-9
    assert not capped.ld_feasible[0] and capped.ld_feasible[-1]
    assert np.all(2 * capped.R[capped.ld_feasible] <= 3.0 + 1e-12)


# ④ 범위 밖 반경, 전부 불가
def test_radius_out_of_range_infeasible(ode_sur):
    big = optimize_volume(ode_sur, _design(), CostParams(), 2000.0, ld_step=1.0)  # R > 2.5 모든 L/D
    assert not big.ld_feasible.any() and np.all(np.isnan(big.total))
    assert big.n_opt is None and any(w.startswith("NO_FEASIBLE") for w in big.warnings)
    json.dumps(big.to_dict())
    small = optimize_volume(ode_sur, _design(), CostParams(), 0.05, ld_step=1.0)  # R < 0.3
    assert not small.ld_feasible.any()


def test_infeasible_ld_total_nan(capped):
    bad = ~capped.ld_feasible
    assert bad.any() and np.all(np.isnan(capped.total[bad]))
    assert np.isfinite(capped.total[~bad]).any()


# ⑤ 최적 칸의 total = 직접 계산
def test_optimum_matches_direct_cost(ode_sur, free):
    d = _design(R=float(free.R_opt), LD=float(free.ld_opt))
    p = Problem(d)
    curve = ode_sur.predict(p.design_matrix(ode_sur, [free.n_opt]))
    direct = cost_arrays(p, [free.n_opt], curve[:, -1])["annual_total"][0]
    assert free.total_opt == pytest.approx(direct, rel=1e-12)
    i = int(np.argmin(np.abs(free.LD - free.ld_opt)))
    j = list(free.N).index(free.n_opt)
    assert free.total[i, j] == free.total_opt == np.nanmin(free.total)


# ⑥ ODE 재검증
def test_ode_verification(free):
    o = free.ode
    assert o is not None and len(o["candidates"]) >= 3
    best = min(c["total_ode"] for c in o["candidates"] if not c["depleted"])
    assert o["recommended"]["total_ode"] == pytest.approx(best)
    # ode_sur이므로 ODE 총비용이 대리모델 총비용과 같다
    assert o["candidates"][0]["total_ode"] == pytest.approx(o["candidates"][0]["total_sur"], rel=1e-6)
    json.dumps(free.to_dict())


def test_verify_false(ode_sur):
    res = optimize_volume(ode_sur, _design(), CostParams(), V, ld_step=0.5, verify=False)
    assert res.ode is None
