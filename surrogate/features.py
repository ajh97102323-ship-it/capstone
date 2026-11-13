"""대리모델 입력 특성 (specs/002 T003, research R2, data-model 1절).

특성 11개 = 설계 입력 10개(로그 스케일 4개는 log10) + `log10_k`.
k는 초기 일일 증발 비율 [1/day]이며 ODE 없이 배열 연산으로 계산한다.

    k = [ q·A_tot·(w + η·(1 − w)) + G_sup·(T_h − T_c) ] / (h_fg · ρ_l · V_tot · fill) × 86400
    q = mli_heat_flux(N, N̄, ε, P_v0, T_h, T_c)   [W/m²]
    w = A_wet(h0) / A_tot                         [-]  초기 젖음 면적 비율, fill과 L/D만의 함수

w는 모듈을 불러올 때 (fill, L/D) 격자에서 `physics.CapsuleTank`로 한 번 계산해 둔 표를 2차원 선형 보간한다.
열유속·상수는 모두 `physics/`의 것을 그대로 쓴다(ODE를 복제하지 않는다, 헌법 원칙 I).
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from physics.geometry import CapsuleTank
from physics.heat import mli_heat_flux
from physics.model import DAY, ETA, H_FG, RHO_L, T_C

INPUT_NAMES = ("N", "Nbar", "eps", "G_sup", "Pv0", "G_out", "S", "R", "LD", "fill")
LOG_INPUTS = ("G_sup", "Pv0", "G_out", "S")  # 이 입력은 log10을 취한다
FEATURE_NAMES = INPUT_NAMES + ("log10_k",)
TH_DEFAULT = 300.0  # 외부 온도 기본값 [K]

# w 표 격자 (fill 0.5~0.95는 91점, L/D 0~3은 61점: 학습 범위와 같다)
W_FILL_GRID = np.linspace(0.5, 0.95, 91)  # 초기 충전율 [-]
W_LD_GRID = np.linspace(0.0, 3.0, 61)     # 실린더 길이비 L/D [-]
_GRID_TOL = 1e-9


def _build_w_table() -> np.ndarray:
    """w[i, j] = A_wet / A_tot, fill = W_FILL_GRID[i], L/D = W_LD_GRID[j]. R=1로 계산한다(R과 무관)."""
    table = np.empty((len(W_FILL_GRID), len(W_LD_GRID)))
    for j, ld in enumerate(W_LD_GRID):
        tank = CapsuleTank(1.0, 2.0 * ld)  # L = 2·R·(L/D)
        h = tank.level(W_FILL_GRID * tank.V_tot)
        table[:, j] = tank.wetted_area(h) / tank.A_tot
    return table


_W_TABLE = _build_w_table()


def wetted_fraction(fill, ld) -> np.ndarray:
    """초기 젖음 면적 비율 w [-]. (fill, L/D) 표의 2차원 선형 보간. 표 범위 밖은 ValueError."""
    fill = np.asarray(fill, dtype=np.float64)
    ld = np.asarray(ld, dtype=np.float64)
    fill, ld = np.broadcast_arrays(fill, ld)
    for name, v, g in (("fill", fill, W_FILL_GRID), ("LD", ld, W_LD_GRID)):
        if not np.all((v >= g[0] - _GRID_TOL) & (v <= g[-1] + _GRID_TOL)):  # NaN도 걸러진다
            raise ValueError(f"{name}가 w 표 범위 [{g[0]}, {g[-1]}] 밖: {v[~((v >= g[0]) & (v <= g[-1]))][:3]}")
    f = np.clip(fill, W_FILL_GRID[0], W_FILL_GRID[-1])
    d = np.clip(ld, W_LD_GRID[0], W_LD_GRID[-1])
    fx = (f - W_FILL_GRID[0]) / (W_FILL_GRID[1] - W_FILL_GRID[0])
    dx = (d - W_LD_GRID[0]) / (W_LD_GRID[1] - W_LD_GRID[0])
    i = np.minimum(np.floor(fx).astype(int), len(W_FILL_GRID) - 2)
    j = np.minimum(np.floor(dx).astype(int), len(W_LD_GRID) - 2)
    a, b = fx - i, dx - j
    T = _W_TABLE
    return ((1 - a) * (1 - b) * T[i, j] + a * (1 - b) * T[i + 1, j]
            + (1 - a) * b * T[i, j + 1] + a * b * T[i + 1, j + 1])


def _check_inputs(X, input_names: Sequence[str]) -> np.ndarray:
    names = list(input_names)
    if names != list(INPUT_NAMES):
        raise ValueError(f"입력 이름·순서가 {list(INPUT_NAMES)}와 같아야 함: {names}")
    X = np.asarray(X, dtype=np.float64)
    if X.ndim != 2 or X.shape[1] != len(INPUT_NAMES):
        raise ValueError(f"X는 (n, {len(INPUT_NAMES)}) 이어야 함: shape {X.shape}")
    return X


def initial_evaporation_rate(X, input_names: Sequence[str], Th: float = TH_DEFAULT) -> np.ndarray:
    """초기 일일 증발 비율 k [1/day]. X는 (n, 10) 물리 단위, `INPUT_NAMES` 순서. Th: 외부 온도 [K]."""
    X = _check_inputs(X, input_names)
    N, Nbar, eps, G_sup, Pv0, _G_out, _S, R, LD, fill = X.T
    L = 2.0 * R * LD                                   # 실린더 길이 [m]
    A_tot = 2.0 * np.pi * R * L + 4.0 * np.pi * R**2   # 내벽 전체 면적 [m²]
    V_tot = np.pi * R**2 * L + 4.0 / 3.0 * np.pi * R**3  # 탱크 체적 [m³]
    w = wetted_fraction(fill, LD)                      # [-]
    q = mli_heat_flux(N, Nbar, eps, Pv0, Th, T_C)      # t=0의 진공압 = Pv0 [W/m²]
    Q0 = q * A_tot * (w + ETA * (1.0 - w)) + G_sup * (Th - T_C)  # 액체로 들어가는 초기 열 [W]
    m0 = fill * RHO_L * V_tot                          # 초기 액체 질량 [kg]
    k = Q0 / (H_FG * m0) * DAY                         # [1/day]
    if not np.all(np.isfinite(k) & (k > 0)):
        raise ValueError("k가 양의 유한한 값이 아님 (입력 오류)")
    return k


def build_features(X, input_names: Sequence[str], Th: float = TH_DEFAULT,
                   log_inputs: Sequence[str] = LOG_INPUTS) -> np.ndarray:
    """설계 입력 (n, 10) → 특성 (n, 11). 로그 스케일 입력은 log10, 마지막 열은 log10(k)."""
    X = _check_inputs(X, input_names)
    k = initial_evaporation_rate(X, input_names, Th)
    Z = np.empty((X.shape[0], len(FEATURE_NAMES)))
    Z[:, :-1] = X
    for j, nm in enumerate(INPUT_NAMES):
        if nm in log_inputs:
            if not np.all(X[:, j] > 0):
                raise ValueError(f"로그 스케일 입력 {nm}은 양수여야 함")
            Z[:, j] = np.log10(X[:, j])
    Z[:, -1] = np.log10(k)
    return Z
