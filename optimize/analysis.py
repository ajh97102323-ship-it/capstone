"""민감도와 Pareto (specs/003 T008·T012, research R7·R10, data-model SensitivityResult·ParetoResult)."""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from physics import BoiloffModel, analytic_optimal_layers

from .layers import _jsonable, ode_scan, optimize_layers
from .problem import Problem, check_variables, cost_arrays

# 경제 변수 -> N 최적값이 움직이는 방향 (+1 비감소, -1 비증가). 수명↑·p_H2↑는 N↑, c_layer↑·할인율↑는 N↓
_DIRECTION = {"p_h2": +1, "c_layer": -1, "life_years": +1, "discount": -1}

# 기본 격자 (research R7)
DEFAULT_GRIDS = {
    "p_h2": np.linspace(2.0, 15.0, 14),         # [$/kg]
    "c_layer": np.linspace(5.0, 30.0, 11),      # [$/(m²·layer)]
    "life_years": np.linspace(10.0, 40.0, 7),   # [yr]
    "discount": np.linspace(0.0, 0.10, 6),      # [-]
}


@dataclass
class SensitivityResult:
    param: str
    values: np.ndarray
    n_sur: np.ndarray        # 대리모델 최적 N (실행 가능한 N이 없으면 NaN)
    total_sur: np.ndarray    # [$/yr]
    n_analytic: np.ndarray   # 근사식 N*
    n_ode: np.ndarray        # ODE 최적 N (계산하지 않은 점은 NaN)
    monotone_ok: bool
    matches_analytic: bool

    def to_dict(self) -> dict:
        return _jsonable({k: getattr(self, k) for k in self.__dataclass_fields__})


@dataclass
class ParetoResult:
    N: np.ndarray            # (k,) int
    capex: np.ndarray        # (k,) [$]
    m_lost: np.ndarray       # (k,) [kg/yr]
    pareto_mask: np.ndarray  # (k,) bool
    n_cost_opt: int | None

    def to_dict(self) -> dict:
        return _jsonable({k: getattr(self, k) for k in self.__dataclass_fields__})


def _monotone(n, direction) -> bool:
    n = np.asarray(n, dtype=float)
    if len(n) < 2 or not np.all(np.isfinite(n)):
        return False
    d = np.diff(n) * direction
    return bool(np.all(d >= 0) and n[-1] != n[0] and (n[-1] - n[0]) * direction > 0)


def sensitivity(sur, problem: Problem, param: str, values, ode_every: int = 3) -> SensitivityResult:
    """경제 변수 하나를 바꿔 가며 대리모델 최적 N, 근사식 N*, ODE 최적 N(ode_every점마다)을 구한다."""
    if param not in _DIRECTION:
        check_variables([param])  # Nbar·eps는 "비용이 정의되지 않음", 그 밖의 이름도 ValueError
        raise ValueError(f"민감도 변수는 {sorted(_DIRECTION)} 중 하나여야 함: {param!r}")
    if int(ode_every) != ode_every or ode_every < 1:
        raise ValueError(f"ode_every는 1 이상의 정수여야 함: {ode_every!r}")
    values = np.asarray(values, dtype=float)
    n = len(values)
    n_sur = np.full(n, np.nan)
    total_sur = np.full(n, np.nan)
    n_an = np.full(n, np.nan)
    n_ode = np.full(n, np.nan)

    problems = [replace(problem, cost=replace(problem.cost, **{param: float(v)})) for v in values]  # 값 검사 포함
    scan = ode_scan(problem) if n else None  # ODE 잔량은 경제 변수와 무관하므로 한 번만 푼다 (비용만 다시 계산)
    ratio_ode = None
    if scan is not None:
        m0 = BoiloffModel(problem.design_params()).m0
        ratio_ode = 1.0 - scan["m_lost"] / m0
    for i, pr in enumerate(problems):
        res = optimize_layers(sur, pr)
        if res.n_opt is not None:
            n_sur[i], total_sur[i] = res.n_opt, res.total_opt
        n_an[i] = analytic_optimal_layers(pr.design_params(), pr.cost)
        if i % ode_every == 0:
            ok = np.flatnonzero(~scan["depleted"])
            if ok.size:
                tot = cost_arrays(pr, scan["N"], ratio_ode)["annual_total"]
                n_ode[i] = scan["N"][ok[int(np.argmin(tot[ok]))]]
    d = _DIRECTION[param]
    return SensitivityResult(param=param, values=values, n_sur=n_sur, total_sur=total_sur, n_analytic=n_an,
                             n_ode=n_ode, monotone_ok=_monotone(n_sur, d),
                             matches_analytic=bool(_monotone(n_an, d) and np.sign(n_sur[-1] - n_sur[0]) == np.sign(n_an[-1] - n_an[0])))


def nondominated(x, y) -> np.ndarray:
    """x, y 모두 작을수록 좋을 때 비지배(다른 점이 하나도 둘 다 ≤이고 하나는 <가 아님) 점의 마스크."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    le = (x[None, :] <= x[:, None]) & (y[None, :] <= y[:, None])  # [i, j]: j가 i보다 둘 다 ≤
    lt = (x[None, :] < x[:, None]) | (y[None, :] < y[:, None])
    return ~np.any(le & lt, axis=1)


def pareto(sur, problem: Problem) -> ParetoResult:
    """MLI 초기 투자비 [$]와 연간 보일오프 질량 [kg/yr]의 Pareto. 실행 가능한 N만 대상, 총비용 최적 N 표시."""
    res = optimize_layers(sur, problem)
    f = res.feasible
    return ParetoResult(N=res.N[f], capex=res.capex[f], m_lost=res.m_lost[f],
                        pareto_mask=nondominated(res.capex[f], res.m_lost[f]), n_cost_opt=res.n_opt)
