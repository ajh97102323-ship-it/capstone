"""MLI 적층 비용 ↔ 보일오프 비용 트레이드오프 테스트."""
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from physics import (CostParams, DesignParams, analytic_optimal_layers, cost_from_curve,
                     cost_vs_layers, evaluate_cost)

NS = range(10, 81, 2)


def _ode_optimum(p, cost):
    d = cost_vs_layers(p, cost, NS)
    return d["N"][np.argmin(d["annual_total"])], d


def test_crf():
    assert CostParams(discount=0.0, life_years=20).crf == pytest.approx(1 / 20)
    # r=5%, Y=20 → 0.08024 (표준 자본회수계수 표)
    assert CostParams(discount=0.05, life_years=20).crf == pytest.approx(0.080243, rel=1e-4)


def test_cost_components_trend_with_layers():
    _, d = _ode_optimum(DesignParams(), CostParams())
    assert np.allclose(np.diff(d["annual_mli"], 2), 0.0, atol=1e-6)   # MLI 비용은 N에 대해 선형
    assert np.all(np.diff(d["annual_mli"]) > 0)
    assert np.all(np.diff(d["annual_boiloff"]) <= 1e-9)               # 보일오프 비용은 N에 대해 감소


def test_total_cost_has_interior_minimum():
    """기본 경제 조건에서 총비용은 U자형이고 최적 적층수가 탐색 범위 내부에 있다."""
    N_opt, d = _ode_optimum(DesignParams(), CostParams())
    assert NS.start < N_opt < NS[-1]
    i = int(np.argmin(d["annual_total"]))
    assert not d["depleted"][i]
    # 최적점에서 두 비용이 같은 크기 (a·N = B/N 이 성립하는 지점)
    assert d["annual_mli"][i] == pytest.approx(d["annual_boiloff"][i], rel=0.3)


@pytest.mark.parametrize("R, LD", [(1.5, 1.0), (2.5, 2.0), (1.0, 0.0)])
def test_analytic_optimum_matches_ode(R, LD):
    p, cost = DesignParams(R=R, LD=LD), CostParams()
    N_opt, _ = _ode_optimum(p, cost)
    assert analytic_optimal_layers(p, cost) == pytest.approx(N_opt, rel=0.12)


@pytest.mark.parametrize("change, more_layers", [
    (dict(p_h2=10.0), True),       # 수소가 비싸면 → 단열을 더 두껍게
    (dict(c_layer=20.0), False),   # MLI가 비싸면 → 적층을 줄임
    (dict(life_years=40.0), True), # 수명이 길면 → 초기 투자 부담 ↓ → 적층 ↑
])
def test_optimum_shifts_with_economics(change, more_layers):
    base, _ = _ode_optimum(DesignParams(), CostParams())
    shifted, _ = _ode_optimum(DesignParams(), replace(CostParams(), **change))
    assert (shifted > base) == more_layers


def test_cost_from_curve_matches_ode():
    """대리모델 후처리용 함수가 ODE 기반 비용과 같은 값을 준다."""
    p, cost = DesignParams(N=50), CostParams()
    res = evaluate_cost(p, cost)
    total, mli, boil = cost_from_curve(p, res.ratio[-1], cost)
    assert total == pytest.approx(res.annual_total, rel=1e-12)
    assert mli == pytest.approx(res.annual_mli, rel=1e-12)
    assert boil == pytest.approx(res.annual_boiloff, rel=1e-12)


def test_depletion_flagged():
    """1년 안에 소진되는 설계는 손실이 m0로 잘리므로 depleted로 표시된다."""
    res = evaluate_cost(DesignParams(N=10, R=0.5, LD=0.0))
    assert res.depleted
    assert res.m_lost == pytest.approx(res.m0, rel=1e-6)
    assert 0 < res.t_empty < 365
    assert not evaluate_cost(DesignParams()).depleted
