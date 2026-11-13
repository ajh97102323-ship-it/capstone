"""체적 고정 N·L/D 격자 최적화 (specs/003 T010, research R6, data-model VolumeResult).

캡슐 체적 V = πR²L + 4/3πR³, L = 2R·LD  ->  R = (V / (π(4/3 + 2·LD)))^(1/3)  [m].
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from physics import DesignParams, evaluate_cost

from .layers import DEPLETION_TOL, _jsonable
from .problem import Problem, cost_arrays


def radius_for_volume(V, LD):
    """체적 V [m³]와 L/D [-]에서 반경 R [m]. LD는 배열 가능."""
    return (np.asarray(V, dtype=float) / (np.pi * (4.0 / 3.0 + 2.0 * np.asarray(LD, dtype=float)))) ** (1.0 / 3.0)


@dataclass
class VolumeResult:
    V: float                   # [m³]
    D_max: float | None        # [m]
    LD: np.ndarray             # (n_LD,) [-]
    N: np.ndarray              # (n_N,) int
    R: np.ndarray              # (n_LD,) [m]
    total: np.ndarray          # (n_LD, n_N) [$/yr], 실행 불가는 NaN
    ld_feasible: np.ndarray    # (n_LD,) bool
    ld_opt: float | None
    n_opt: int | None
    total_opt: float | None    # [$/yr]
    R_opt: float | None        # [m]
    ode: dict | None
    warnings: list

    def to_dict(self) -> dict:
        return _jsonable({k: getattr(self, k) for k in self.__dataclass_fields__})


def _range_of(sur, name):
    tr = sur.train_range
    j = tr["names"].index(name)
    return float(tr["lo"][j]), float(tr["hi"][j])


def optimize_volume(sur, design: dict, cost, V: float, D_max=None, ld_step: float = 0.05,
                    verify: bool = True, top_k: int = 5) -> VolumeResult:
    """체적 V를 고정하고 L/D 격자 × N 정수 격자를 전수 탐색한다. design의 R·LD·N은 무시한다.

    실행 불가: 반경이 학습 범위 밖, 직경 2R > D_max, 365일 잔량비 < DEPLETION_TOL(소진). 불가 칸은 NaN.
    """
    if not V > 0:
        raise ValueError(f"V > 0 이어야 함: {V!r} [m3]")
    if D_max is not None and not D_max > 0:
        raise ValueError(f"D_max > 0 이어야 함: {D_max!r} [m]")
    if not ld_step > 0:
        raise ValueError(f"ld_step > 0 이어야 함: {ld_step!r}")
    ld_lo, ld_hi = _range_of(sur, "LD")
    r_lo, r_hi = _range_of(sur, "R")
    n_lo, n_hi = _range_of(sur, "N")
    LD = np.arange(ld_lo, ld_hi + ld_step * 1e-6, ld_step)
    N = np.arange(int(n_lo), int(n_hi) + 1, dtype=int)
    R = radius_for_volume(V, LD)
    ld_ok = (R >= r_lo) & (R <= r_hi)
    if D_max is not None:
        ld_ok &= 2.0 * R <= D_max
    base = {k: v for k, v in design.items() if k not in ("R", "LD", "N")}
    total = np.full((len(LD), len(N)), np.nan)
    warnings: list[str] = []

    for i in np.flatnonzero(ld_ok):
        pr = Problem({**base, "R": float(R[i]), "LD": float(LD[i])}, cost, n_range=(int(n_lo), int(n_hi)))
        pr.check(sur)  # 나머지 입력이 학습 범위 밖이면 OutOfRangeError
        ratio365 = np.asarray(sur.predict(pr.design_matrix(sur, N)))[:, -1]
        t = cost_arrays(pr, N, ratio365)["annual_total"]
        total[i] = np.where(ratio365 < DEPLETION_TOL, np.nan, t)

    n_opt = ld_opt = total_opt = R_opt = None
    ode = None
    if np.isfinite(total).any():
        flat = int(np.nanargmin(total))
        i, j = divmod(flat, len(N))
        ld_opt, n_opt, total_opt, R_opt = float(LD[i]), int(N[j]), float(total[i, j]), float(R[i])
        if ld_opt >= LD[-1] - 1e-9:
            warnings.append(f"LD_BOUNDARY: 최적 L/D가 학습 범위 상한 {LD[-1]:g}")
        if verify:
            ode = _verify(total, LD, N, R, base, cost, top_k)
    else:
        warnings.append("NO_FEASIBLE: 반경·직경 제약과 소진 조건을 만족하는 (L/D, N)이 없음")
    return VolumeResult(V=float(V), D_max=None if D_max is None else float(D_max), LD=LD, N=N, R=R, total=total,
                        ld_feasible=ld_ok, ld_opt=ld_opt, n_opt=n_opt, total_opt=total_opt, R_opt=R_opt,
                        ode=ode, warnings=warnings)


def _verify(total, LD, N, R, base, cost, top_k) -> dict:
    """대리모델 총비용 상위 top_k개 (L/D, N)를 ODE로 재계산하고 ODE 총비용 최소를 추천한다."""
    flat_total = np.where(np.isfinite(total), total, np.inf).ravel()
    order = np.argsort(flat_total, kind="stable")[:max(top_k, 3)]
    cands = []
    for k in order:
        if not np.isfinite(flat_total[k]):
            continue
        i, j = divmod(int(k), len(N))
        r = evaluate_cost(DesignParams(**{**base, "R": float(R[i]), "LD": float(LD[i]), "N": float(N[j])}), cost)
        cands.append({"N": int(N[j]), "LD": float(LD[i]), "R": float(R[i]), "total_sur": float(total[i, j]),
                      "total_ode": float(r.annual_total), "depleted": bool(r.depleted)})
    live = [c for c in cands if not c["depleted"]]
    rec = min(live, key=lambda c: c["total_ode"]) if live else None
    return {"candidates": cands, "recommended": rec}
