"""샘플 하나의 시뮬레이션과 품질 필터 (specs/001 T016, research R6, FR-006~008·010).

곡선과 보조 출력은 모두 physics.BoiloffModel로 계산한다(헌법 원칙 I). ODE 풀이기는 t=0에서 1.0 대신
1 − 2e-16 같은 값을 돌려줄 수 있으므로, 첫 값이 1에서 1e-12 이내면 이 데이터 단계에서만 정확히 1.0으로
맞춘다(physics/는 고치지 않음, 검증 1회차 발견 #3).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from data.config import InputSpec
from physics import BoiloffModel, DesignParams

TOL_ABOVE_ONE = 1e-9    # 잔량비 상한 여유 [-]
TOL_INCREASE = 1e-9     # 인접 시점 증가 허용 [-] (ODE rtol 1e-8보다 작음)
TOL_INITIAL = 1e-12     # 첫 시점 잔량비와 1의 차이 허용 [-]

AUX_NAMES = ("Q0", "m0", "m_lost", "A_mli", "t_empty")  # [W], [kg], [kg], [m²], [day]
REASONS = ("solver_error", "nan", "negative", "above_one", "increasing", "initial_not_one")


@dataclass
class SampleResult:
    Y: np.ndarray        # 잔량비 곡선 float64 (n_points,), Y[0] == 1.0
    aux: np.ndarray      # float64 (5,), AUX_NAMES 순서
    depleted: bool       # isfinite(t_empty)


@dataclass
class Rejection:
    reason: str          # REASONS 중 하나
    detail: str          # 예외 메시지 또는 위반 위치(시점 인덱스)


def validate_curve(Y: np.ndarray) -> tuple[str, str] | None:
    """research R6 표의 조건을 차례로 검사한다. 위반이 없으면 None, 있으면 (사유 코드, 상세)."""
    Y = np.asarray(Y, dtype=np.float64)
    bad = np.nonzero(~np.isfinite(Y))[0]
    if bad.size:
        return "nan", f"non-finite at index {int(bad[0])}: {Y[bad[0]]!r}"
    bad = np.nonzero(Y < 0.0)[0]
    if bad.size:
        return "negative", f"Y[{int(bad[0])}]={Y[bad[0]]!r} < 0"
    bad = np.nonzero(Y > 1.0 + TOL_ABOVE_ONE)[0]
    if bad.size:
        return "above_one", f"Y[{int(bad[0])}]={Y[bad[0]]!r} > 1 + {TOL_ABOVE_ONE:g}"
    d = np.diff(Y)
    bad = np.nonzero(d > TOL_INCREASE)[0]
    if bad.size:
        i = int(bad[0])
        return "increasing", f"Y[{i + 1}] - Y[{i}] = {d[i]!r} > {TOL_INCREASE:g}"
    if abs(Y[0] - 1.0) > TOL_INITIAL:
        return "initial_not_one", f"Y[0]={Y[0]!r}"
    return None


def run_sample(x: Sequence[float], inputs: Sequence[InputSpec], cfg) -> SampleResult | Rejection:
    """입력 한 행 x(inputs 순서, 물리 단위)를 시뮬레이션해 SampleResult 또는 Rejection을 돌려준다."""
    names = [s.name for s in inputs]
    try:
        p = DesignParams(**dict(zip(names, (float(v) for v in x))), **cfg.fixed)
        model = BoiloffModel(p)
        _, ratio, t_empty = model.simulate_detailed(cfg.days, cfg.n_points)
        m0 = float(model.m0)                              # [kg]
        Q0 = float(model.heat_to_liquid(0.0, model.m0))   # [W]
        A_mli = float(model.tank.A_tot)                   # [m²]
    except KeyboardInterrupt:
        raise
    except Exception as e:  # noqa: BLE001 — 시뮬레이션 실패는 모두 제외 사유로 기록
        return Rejection("solver_error", f"{type(e).__name__}: {e}")

    Y = np.array(ratio, dtype=np.float64)
    problem = validate_curve(Y)
    if problem is not None:
        return Rejection(*problem)
    Y[0] = 1.0  # |Y[0] − 1| ≤ 1e-12 확인됨 (initial_not_one 아님)

    t_empty = float(t_empty)                              # [day], 소진 없으면 +inf
    m_lost = m0 * (1.0 - Y[-1])                           # [kg]
    aux = np.array([Q0, m0, m_lost, A_mli, t_empty], dtype=np.float64)
    if not np.all(np.isfinite(aux[:4])) or np.isnan(t_empty) or t_empty == -np.inf:
        return Rejection("nan", f"aux non-finite: {dict(zip(AUX_NAMES, aux.tolist()))}")
    return SampleResult(Y=Y, aux=aux, depleted=bool(np.isfinite(t_empty)))
