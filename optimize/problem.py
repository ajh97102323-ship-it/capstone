"""최적화 문제 정의, 변수 검사, 비용 후처리 (specs/003 T002, research R1, data-model Problem).

경제 변수(c_layer, p_h2, 수명, 할인율)는 `physics.CostParams`로만 다루고 대리모델 입력에 넣지 않는다(헌법 IV).
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields

import numpy as np

from physics import BoiloffModel, CostParams, DesignParams
from physics.cost import mli_area, mli_capex

DEFAULT_MODEL = "models/mlp_lhs_n500_seed42_seed0_tuned"  # 002 최종 모델 (500개 데이터셋, Optuna 30회; 사용자 지시로 데이터 축소)
DEPLETION_TOL = 0.03  # [-] 대리모델 365일 잔량비가 이보다 작으면 소진으로 보고 후보에서 제외 (research R3)

_ALLOWED_VARS = ("N", "LD")
_UNPRICED = {"Nbar": "적층밀도 N̄", "eps": "실드 방사율 ε"}
_DESIGN_KEYS = tuple(f.name for f in fields(DesignParams))


def check_variables(names) -> None:
    """최적화 변수는 N, LD만 허용한다. N̄·ε는 비용 모델에 가격이 없어 최적화하면 무의미(헌법 IV)."""
    for n in names:
        if n in _ALLOWED_VARS:
            continue
        if n in _UNPRICED:
            raise ValueError(f"{n}({_UNPRICED[n]})은 최적화 변수가 될 수 없음: 비용이 정의되지 않음 (허용: {_ALLOWED_VARS})")
        raise ValueError(f"알 수 없는 최적화 변수 {n!r} (허용: {_ALLOWED_VARS})")


@dataclass
class Problem:
    """고정 설계 + 경제 변수 + 제약. design의 N은 설계변수라 무시한다(없는 키는 DesignParams 기본값)."""

    design: dict
    cost: CostParams = field(default_factory=CostParams)
    n_range: tuple = (10, 120)
    residual: tuple | None = None   # (t_day [day], min_ratio [-])

    def __post_init__(self):
        extra = sorted(set(self.design) - set(_DESIGN_KEYS))
        if extra:
            raise ValueError(f"알 수 없는 설계 입력: {extra} (허용: {list(_DESIGN_KEYS)})")
        c = self.cost
        if not 0 < c.life_years < np.inf:
            raise ValueError(f"life_years > 0 이어야 함: {c.life_years!r} [yr]")
        if not 0 < c.p_h2 < np.inf:
            raise ValueError(f"p_h2 > 0 이어야 함: {c.p_h2!r} [$/kg]")
        if not 0 < c.c_layer < np.inf:
            raise ValueError(f"c_layer > 0 이어야 함: {c.c_layer!r} [$/(m²·layer)]")
        if not 0 <= c.c_fixed < np.inf:
            raise ValueError(f"c_fixed >= 0 이어야 함: {c.c_fixed!r} [$/m²]")
        if not 0 <= c.discount < np.inf:
            raise ValueError(f"discount >= 0 이어야 함: {c.discount!r} [-]")
        lo, hi = self.n_range
        if int(lo) != lo or int(hi) != hi or not lo <= hi:
            raise ValueError(f"n_range는 lo <= hi인 정수 쌍이어야 함: {self.n_range!r}")
        self.n_range = (int(lo), int(hi))
        if self.residual is not None:
            t_day, r = self.residual
            if not (0 < t_day <= 365) or not (0 <= r <= 1):
                raise ValueError(f"residual=(t_day in (0,365], min_ratio in [0,1]) 이어야 함: {self.residual!r}")

    # ---------- 설계 ----------

    def design_params(self, N=None) -> DesignParams:
        """N을 지정한 DesignParams. N이 없으면 design의 N(없으면 DesignParams 기본값)."""
        d = dict(self.design)
        if N is not None:
            d["N"] = float(N)
        return DesignParams(**d)

    def design_matrix(self, sur, Ns) -> np.ndarray:
        """대리모델 입력 (len(Ns), n_inputs). 열 순서는 sur.input_names, N 열은 Ns."""
        Ns = np.asarray(Ns, dtype=np.float64)
        base = self.design_params()
        X = np.empty((len(Ns), len(sur.input_names)))
        for j, name in enumerate(sur.input_names):
            X[:, j] = Ns if name == "N" else getattr(base, name)
        return X

    def check(self, sur) -> None:
        """학습 범위 검사: n_range가 N의 학습 범위 안인지(ValueError), 설계 입력이 범위 안인지(OutOfRangeError)."""
        tr = sur.train_range
        j = tr["names"].index("N")
        lo, hi = tr["lo"][j], tr["hi"][j]
        if self.n_range[0] < lo or self.n_range[1] > hi:
            raise ValueError(f"n_range {self.n_range}가 학습 범위 N [{lo:g}, {hi:g}] 밖")
        sur.check_range(self.design_matrix(sur, np.array(self.n_range)))


def cost_arrays(problem: Problem, N, ratio365) -> dict:
    """N 배열과 365일 잔량비 배열에서 비용을 계산한다. 식은 physics.cost 그대로(research R1).

    반환(모두 (k,)): annual_mli, annual_boiloff, annual_total [$/yr], capex [$], m_lost [kg/yr]
    """
    N = np.asarray(N, dtype=np.float64)
    ratio365 = np.asarray(ratio365, dtype=np.float64)
    cost = problem.cost
    model = BoiloffModel(problem.design_params())  # 형상(R, LD, fill)은 N과 무관
    capex = mli_capex(N, mli_area(model), cost)
    m_lost = model.m0 * (1.0 - ratio365)
    annual_mli = capex * cost.crf
    annual_boiloff = cost.p_h2 * m_lost
    return {"annual_mli": annual_mli, "annual_boiloff": annual_boiloff,
            "annual_total": annual_mli + annual_boiloff, "capex": capex, "m_lost": m_lost}
