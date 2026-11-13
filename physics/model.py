"""LH2 탱크 보일오프 간이 모델: dm/dt = −Q_L / h_fg."""
from dataclasses import dataclass

import numpy as np
from scipy.integrate import solve_ivp

from .geometry import CapsuleTank
from .heat import mli_heat_flux, vacuum_pressure

H_FG = 446e3      # 증발잠열 [J/kg]
T_C = 20.3        # LH2 온도 [K]
RHO_L = 70.8      # 액체 밀도 [kg/m³]
ETA = 0.1         # 기상부 벽 열 중 액체에 도달하는 비율
GAP_EXTRA = 0.02  # MLI 외 진공 공간 여유 두께 [m]
DAY = 86400.0
SIM_DAYS = 365.0  # 액위 변화(젖음 면적 감소) 효과가 곡선에 드러나도록 1년


@dataclass
class DesignParams:
    N: float = 40          # MLI 적층수
    Nbar: float = 20       # 적층밀도 [layers/cm]
    eps: float = 0.03      # 실드 방사율
    G_sup: float = 1e-3    # 지지구조 컨덕턴스 [W/K]
    Pv0: float = 1e-3      # 초기 진공압 [Pa]
    G_out: float = 1e-8    # 아웃개싱 [Pa·m³/s]
    S: float = 1e-3        # 게터 배기속도 [m³/s]
    R: float = 1.5         # 반경 [m]
    LD: float = 1.0        # 실린더 길이비 L/D
    fill: float = 0.9      # 초기 충전율
    Th: float = 300.0      # 외부 온도 [K]


class BoiloffModel:
    def __init__(self, p: DesignParams):
        self.p = p
        self.tank = CapsuleTank(p.R, p.LD * 2 * p.R)
        mli_thickness = p.N / p.Nbar / 100.0  # [m]
        self.V_vac = self.tank.A_tot * (mli_thickness + GAP_EXTRA)
        self.m0 = p.fill * RHO_L * self.tank.V_tot

    def heat_to_liquid(self, t, m):
        """시각 t, 액체 질량 m에서 액체로 들어가는 열 [W]."""
        p, tank = self.p, self.tank
        h = tank.level(max(m, 0.0) / RHO_L)
        A_w = tank.wetted_area(h)
        Pv = vacuum_pressure(t, p.Pv0, p.G_out, p.S, self.V_vac)
        q = mli_heat_flux(p.N, p.Nbar, p.eps, Pv, p.Th, T_C)
        return q * (A_w + ETA * (tank.A_tot - A_w)) + p.G_sup * (p.Th - T_C)

    def _rhs(self, t, y):
        return [-self.heat_to_liquid(t, y[0]) / H_FG]

    def simulate(self, days: float = SIM_DAYS, n_points: int = 100):
        """반환: (t [day], 잔량비 m/m0). 액체가 소진되면 이후 값은 0."""
        t, ratio, _ = self.simulate_detailed(days, n_points)
        return t, ratio

    def simulate_detailed(self, days: float = SIM_DAYS, n_points: int = 100):
        """반환: (t [day], 잔량비 m/m0, t_empty [day]).

        t_empty는 ODE 소진 이벤트 시각이며, 기간 안에 소진되지 않으면 np.inf.
        액체가 소진되면 이후 잔량비는 0 (specs/001 research R4).
        """
        t_eval = np.linspace(0.0, days * DAY, n_points)

        def empty(t, y):
            return y[0]
        empty.terminal, empty.direction = True, -1

        sol = solve_ivp(self._rhs, (0.0, t_eval[-1]), [self.m0], t_eval=t_eval,
                        events=empty, method="LSODA", rtol=1e-8, atol=1e-6)
        if not sol.success:
            raise RuntimeError(sol.message)
        ratio = np.zeros(n_points)
        ratio[: sol.y.shape[1]] = np.clip(sol.y[0] / self.m0, 0.0, 1.0)
        t_empty = sol.t_events[0][0] / DAY if sol.t_events[0].size else np.inf  # [day]
        return t_eval / DAY, ratio, t_empty


def simulate(p: DesignParams, days: float = SIM_DAYS, n_points: int = 100):
    return BoiloffModel(p).simulate(days, n_points)
