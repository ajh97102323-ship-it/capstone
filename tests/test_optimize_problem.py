"""optimize/problem.py 테스트 (specs/003 T001)."""
from dataclasses import replace

import numpy as np
import pytest

from physics import CostParams, DesignParams, cost_from_curve, simulate
from surrogate import OutOfRangeError

from optimize.problem import DEFAULT_MODEL, DEPLETION_TOL, Problem, check_variables, cost_arrays


def _design(**kw):
    d = {k: v for k, v in vars(DesignParams()).items() if k != "Th"}
    d.update(kw)
    return d


def test_constants():
    assert DEPLETION_TOL == 0.03
    assert isinstance(DEFAULT_MODEL, str) and DEFAULT_MODEL


def test_cost_arrays_matches_cost_from_curve(ode_sur):
    cost = CostParams(c_layer=12.0, c_fixed=40.0, p_h2=7.0, life_years=15.0, discount=0.06)
    prob = Problem(_design(), cost)
    Ns = np.array([10, 25, 40, 77, 120])
    ratio = np.array([0.35, 0.6, 0.72, 0.85, 0.9])
    arr = cost_arrays(prob, Ns, ratio)
    for i, N in enumerate(Ns):
        p = DesignParams(**{**_design(), "N": float(N)})
        tot, mli, boil = cost_from_curve(p, ratio[i], cost)
        assert arr["annual_total"][i] == pytest.approx(tot, rel=1e-12)
        assert arr["annual_mli"][i] == pytest.approx(mli, rel=1e-12)
        assert arr["annual_boiloff"][i] == pytest.approx(boil, rel=1e-12)
    # capex·CRF = annual_mli, m_lost·p_h2 = annual_boiloff
    assert np.allclose(arr["capex"] * cost.crf, arr["annual_mli"], rtol=1e-12)
    assert np.allclose(arr["m_lost"] * cost.p_h2, arr["annual_boiloff"], rtol=1e-12)


def test_check_variables_ok():
    check_variables(["N", "LD"])
    check_variables(["N"])


@pytest.mark.parametrize("name", ["Nbar", "eps"])
def test_check_variables_rejects_unpriced(name):
    with pytest.raises(ValueError, match="비용"):
        check_variables([name])


def test_check_variables_rejects_unknown():
    with pytest.raises(ValueError):
        check_variables(["foo"])
    with pytest.raises(ValueError):
        check_variables(["N", "eps"])


@pytest.mark.parametrize("kw", [
    dict(life_years=0.0), dict(life_years=-1.0), dict(p_h2=0.0), dict(p_h2=-3.0),
    dict(c_layer=0.0), dict(c_layer=-1.0), dict(discount=-0.01), dict(c_fixed=-1.0),
])
def test_bad_economics_raise(kw):
    with pytest.raises(ValueError):
        Problem(_design(), CostParams(**kw))


def test_discount_zero_allowed():
    Problem(_design(), CostParams(discount=0.0))


def test_default_cost_and_range():
    prob = Problem(_design())
    assert prob.cost == CostParams() and prob.n_range == (10, 120) and prob.residual is None


def test_bad_n_range_raises():
    with pytest.raises(ValueError):
        Problem(_design(), n_range=(50, 20))


def test_design_out_of_range_raises(ode_sur):
    with pytest.raises(OutOfRangeError):
        Problem(_design(R=5.0)).check(ode_sur)
    with pytest.raises(OutOfRangeError):
        Problem(_design(fill=0.99)).check(ode_sur)
    Problem(_design()).check(ode_sur)  # 정상은 통과


def test_n_range_outside_training_range_raises(ode_sur):
    with pytest.raises(ValueError):
        Problem(_design(), n_range=(5, 120)).check(ode_sur)
    with pytest.raises(ValueError):
        Problem(_design(), n_range=(10, 200)).check(ode_sur)
    Problem(_design(), n_range=(20, 100)).check(ode_sur)


def test_design_matrix_and_params(ode_sur):
    prob = Problem(_design(R=1.1))
    X = prob.design_matrix(ode_sur, np.array([10, 50, 120]))
    assert X.shape == (3, 10)
    assert X[:, ode_sur.input_names.index("N")].tolist() == [10, 50, 120]
    assert np.all(X[:, ode_sur.input_names.index("R")] == 1.1)
    assert prob.design_params(33).N == 33 and prob.design_params(33).R == 1.1
