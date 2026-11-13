"""적층수 N 최적화와 ODE 재검증 (specs/003 T004, research R2~R5, data-model LayerResult·Verification).

`optimize_layers`는 대리모델만 쓴다(ODE 없음, 1초 이내). `verify_with_ode`가 상위 후보와 전 범위를 ODE로 재계산한다.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from physics import analytic_optimal_layers, cost_vs_layers, simulate

from .problem import DEPLETION_TOL, Problem, cost_arrays

FLAT_TOL = 0.01  # 평평한 구간: 총비용 ≤ 최소 × (1 + FLAT_TOL)  (research R5)


def _jsonable(o):
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return _jsonable(o.tolist())
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, float) and not np.isfinite(o):
        return None  # JSON에는 NaN/inf가 없다
    return o


@dataclass
class LayerResult:
    N: np.ndarray                 # (k,) int
    t: np.ndarray                 # (100,) [day]
    ratio365: np.ndarray          # (k,) [-]
    curves: np.ndarray            # (k, 100) [-]
    annual_mli: np.ndarray        # (k,) [$/yr]
    annual_boiloff: np.ndarray    # (k,) [$/yr]
    annual_total: np.ndarray      # (k,) [$/yr]
    capex: np.ndarray             # (k,) [$]
    m_lost: np.ndarray            # (k,) [kg/yr]
    depleted: np.ndarray          # (k,) bool
    residual_ok: np.ndarray       # (k,) bool
    feasible: np.ndarray          # (k,) bool
    n_opt: int | None
    total_opt: float | None       # [$/yr]
    flat: tuple | None
    n_unconstrained: int | None
    warnings: list = field(default_factory=list)
    elapsed_s: float = 0.0        # [s]
    n_closest: int | None = None  # 잔량 제약을 만족하는 N이 없을 때, 그 시점 잔량비가 가장 큰 N

    def to_dict(self) -> dict:
        return _jsonable({k: getattr(self, k) for k in self.__dataclass_fields__})


@dataclass
class Verification:
    candidates: list              # 대리모델 총비용 순 상위 N
    candidate_totals_ode: list    # [$/yr]
    n_recommended: int | None
    scan: dict                    # ode_scan 결과
    n_ode: int | None
    total_ode: float | None       # [$/yr]
    total_ode_at_sur: float | None  # [$/yr]
    rel_cost_err: float | None    # [-]
    dN: int | None
    n_analytic: float

    def to_dict(self) -> dict:
        return _jsonable({k: getattr(self, k) for k in self.__dataclass_fields__})


def optimize_layers(sur, problem: Problem) -> LayerResult:
    """대리모델 배치 예측 한 번으로 N 전 범위의 비용을 계산하고 실행 가능 후보 중 총비용 최소 N을 고른다."""
    t0 = time.perf_counter()
    problem.check(sur)
    N = np.arange(problem.n_range[0], problem.n_range[1] + 1, dtype=int)
    curves = np.asarray(sur.predict(problem.design_matrix(sur, N)))
    ratio365 = curves[:, -1]
    c = cost_arrays(problem, N, ratio365)

    invalid = ~np.isfinite(curves).all(axis=1)  # 대리모델 출력이 NaN/inf인 후보는 실행 불가
    depleted = (ratio365 < DEPLETION_TOL) & ~invalid
    t_grid = np.asarray(sur.t, dtype=float)
    if problem.residual is None:
        residual_ok = np.ones(len(N), dtype=bool)
    else:  # research R9: 대리모델 곡선을 목표 시점으로 보간
        t_day, r_min = problem.residual
        at_t = np.array([np.interp(t_day, t_grid, cv) for cv in curves])
        residual_ok = at_t >= r_min
    residual_ok = residual_ok & ~invalid
    feasible = ~depleted & residual_ok & ~invalid
    warnings: list[str] = []
    if invalid.any():
        warnings.append(f"NONFINITE_EXCLUDED: 대리모델 출력이 NaN/inf인 N {int(invalid.sum())}개를 후보에서 제외")
    n_dep = int(depleted.sum())
    if n_dep:
        warnings.append(f"DEPLETED_EXCLUDED: 365일 잔량비 < {DEPLETION_TOL}인 N {n_dep}개를 후보에서 제외")

    total = c["annual_total"]
    n_opt = total_opt = flat = n_closest = None
    n_unconstrained = None
    free = ~depleted & ~invalid
    if free.any():
        idx = np.flatnonzero(free)
        n_unconstrained = int(N[idx[int(np.argmin(total[idx]))]])
    if feasible.any():
        idx = np.flatnonzero(feasible)
        i = idx[int(np.argmin(total[idx]))]
        n_opt, total_opt = int(N[i]), float(total[i])
        near = N[feasible & (total <= total_opt * (1.0 + FLAT_TOL))]
        flat = (int(near.min()), int(near.max()))
        if n_opt == problem.n_range[1]:
            warnings.append(f"BOUNDARY_HIGH: 최적 N이 범위 상한 {n_opt}. 더 많은 적층이 유리할 수 있어 범위 확장 검토")
        if n_opt == problem.n_range[0]:
            warnings.append(f"BOUNDARY_LOW: 최적 N이 범위 하한 {n_opt}. 더 적은 적층이 유리할 수 있어 범위 확장 검토")
        if n_opt != n_unconstrained:
            warnings.append(f"RESIDUAL_ACTIVE: 잔량 제약 때문에 무제약 최적 N={n_unconstrained}과 다름")
    elif problem.residual is not None and free.any():
        idx = np.flatnonzero(free)
        n_closest = int(N[idx[int(np.argmax(at_t[idx]))]])
        warnings.append(f"RESIDUAL_INFEASIBLE: {problem.residual[0]:g}일 잔량비 >= {problem.residual[1]:g}인 N이 없음. "
                        f"가장 가까운 N={n_closest} (잔량비 {at_t[n_closest - problem.n_range[0]]:.4f})")
    else:
        warnings.append("NO_FEASIBLE: 실행 가능한 N이 없음")

    return LayerResult(
        N=N, t=np.asarray(sur.t, dtype=float), ratio365=ratio365, curves=curves,
        annual_mli=c["annual_mli"], annual_boiloff=c["annual_boiloff"], annual_total=total,
        capex=c["capex"], m_lost=c["m_lost"], depleted=depleted, residual_ok=residual_ok, feasible=feasible,
        n_opt=n_opt, total_opt=total_opt, flat=flat, n_unconstrained=n_unconstrained, warnings=warnings,
        elapsed_s=time.perf_counter() - t0, n_closest=n_closest,
    )


def ode_scan(problem: Problem) -> dict:
    """ODE로 n_range 전 범위의 비용을 계산한다. `physics.cost_vs_layers`와 같은 키."""
    lo, hi = problem.n_range
    return cost_vs_layers(problem.design_params(), problem.cost, range(lo, hi + 1))


def analytic_n(problem: Problem) -> float:
    """근사식 N* = sqrt(B/a) (physics.analytic_optimal_layers). 기준 N은 design의 N(없으면 기본값)."""
    return float(analytic_optimal_layers(problem.design_params(), problem.cost))


def verify_with_ode(problem: Problem, result: LayerResult, top_k: int = 5) -> Verification:
    """대리모델 상위 후보 top_k개와 N 전 범위를 ODE로 재검증한다 (research R4). 최종 보고 값은 ODE 값."""
    if top_k < 3:
        raise ValueError(f"top_k >= 3 이어야 함: {top_k}")
    scan = ode_scan(problem)
    lo = problem.n_range[0]
    n_analytic = analytic_n(problem)
    total, dep = scan["annual_total"], scan["depleted"]

    idx = np.flatnonzero(result.feasible)
    order = idx[np.argsort(result.annual_total[idx], kind="stable")][:top_k]
    candidates = [int(result.N[i]) for i in order]
    cand_totals = [float(total[n - lo]) for n in candidates]

    live = [(c, n) for c, n in zip(cand_totals, candidates) if not dep[n - lo]]  # ODE에서 소진된 후보는 추천 제외
    if problem.residual is not None:  # 잔량 목표도 ODE로 다시 확인 (research R9)
        t_day, r_min = problem.residual
        def ode_ok(n):
            t, ratio = simulate(problem.design_params(n), days=365.0, n_points=366)
            return float(np.interp(t_day, t, ratio)) >= r_min
        live = [(c, n) for c, n in live if ode_ok(n)]
    n_recommended = min(live)[1] if live else None

    ok = np.flatnonzero(~dep)
    n_ode = total_ode = None
    if ok.size:
        i = ok[int(np.argmin(total[ok]))]
        n_ode, total_ode = int(scan["N"][i]), float(total[i])

    total_at_sur = rel = dN = None
    if result.n_opt is not None:
        total_at_sur = float(total[result.n_opt - lo])
        if total_ode is not None:
            rel = (total_at_sur - total_ode) / total_ode
            dN = result.n_opt - n_ode
    return Verification(candidates=candidates, candidate_totals_ode=cand_totals, n_recommended=n_recommended,
                        scan=scan, n_ode=n_ode, total_ode=total_ode, total_ode_at_sur=total_at_sur,
                        rel_cost_err=rel, dN=dN, n_analytic=n_analytic)
