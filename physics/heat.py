"""MLI 열유속(Lockheed 반경험식)과 단열 진공압 모델."""
import numpy as np

PA_TO_TORR = 1 / 133.322

# Lockheed 식 계수 (q: W/m², N̄: layers/cm, P: torr). 원 출처: Keller et al. (1974)
C_S, EXP_S = 8.95e-8, 2.56
C_R = 5.39e-10
C_G = 1.46e4


def mli_heat_flux(N, Nbar, eps, P_pa, Th, Tc):
    """MLI를 통과하는 열유속 [W/m²]. 고체 전도 + 복사 + 잔류가스 전도."""
    Tm = 0.5 * (Th + Tc)
    P = P_pa * PA_TO_TORR
    q_solid = C_S * Nbar**EXP_S * Tm * (Th - Tc)
    q_rad = C_R * eps * (Th**4.67 - Tc**4.67)
    q_gas = C_G * P * (Th**0.52 - Tc**0.52)
    return (q_solid + q_rad + q_gas) / N


def vacuum_pressure(t, Pv0, G, S, V_vac):
    """진공압 P_v(t) [Pa]. dP/dt = (G − S·P)/V_vac 의 해석해."""
    P_eq = G / S
    return P_eq + (Pv0 - P_eq) * np.exp(-S * t / V_vac)
