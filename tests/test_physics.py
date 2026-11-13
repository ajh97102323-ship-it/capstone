"""물리 모델 테스트: 형상, 열유속, 진공압, 보일오프 ODE."""
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from scipy.integrate import quad, trapezoid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from physics import BoiloffModel, CapsuleTank, DesignParams, mli_heat_flux, simulate, vacuum_pressure
from physics.model import DAY, H_FG, T_C


# ---------------------------------------------------------------- 형상

def _segment_area(r, d):
    """반경 r인 원에서 바닥부터 깊이 d까지의 활꼴 면적."""
    d = np.clip(d, 0, 2 * r)
    return r**2 * np.arccos((r - d) / r) - (r - d) * np.sqrt(2 * r * d - d**2)


def _volume_by_slicing(R, L, h):
    """탱크 축 방향으로 단면을 적분한 독립적인 체적 계산 (검산용)."""
    def cap_slice(x):  # 반구부: 축에서 x만큼 떨어진 단면은 반경 sqrt(R²−x²)인 원
        r = np.sqrt(max(R**2 - x**2, 0.0))
        return _segment_area(r, h - (R - r)) if r > 0 else 0.0
    caps = 2 * quad(cap_slice, 0, R, limit=200)[0]
    return L * _segment_area(R, h) + caps


@pytest.mark.parametrize("R, L", [(1.0, 0.0), (1.5, 3.0), (0.8, 5.0)])
def test_full_and_empty(R, L):
    tank = CapsuleTank(R, L)
    assert tank.volume(0.0) == pytest.approx(0.0, abs=1e-12)
    assert tank.wetted_area(0.0) == pytest.approx(0.0, abs=1e-12)
    assert tank.volume(2 * R) == pytest.approx(tank.V_tot, rel=1e-12)
    assert tank.wetted_area(2 * R) == pytest.approx(tank.A_tot, rel=1e-12)


@pytest.mark.parametrize("R, L", [(1.0, 0.0), (1.5, 3.0)])
def test_half_fill_symmetry(R, L):
    tank = CapsuleTank(R, L)
    assert tank.volume(R) == pytest.approx(tank.V_tot / 2, rel=1e-12)
    assert tank.wetted_area(R) == pytest.approx(tank.A_tot / 2, rel=1e-12)


def test_sphere_limit():
    R = 1.2
    tank = CapsuleTank(R, 0.0)
    for h in np.linspace(0, 2 * R, 9):
        assert tank.volume(h) == pytest.approx(np.pi * h**2 * (3 * R - h) / 3, abs=1e-12)
        assert tank.wetted_area(h) == pytest.approx(2 * np.pi * R * h, abs=1e-12)


@pytest.mark.parametrize("h_frac", [0.1, 0.3, 0.5, 0.75, 0.95])
def test_volume_matches_slicing_integration(h_frac):
    R, L = 1.5, 3.0
    h = h_frac * 2 * R
    assert CapsuleTank(R, L).volume(h) == pytest.approx(_volume_by_slicing(R, L, h), rel=1e-6)


def test_volume_monotonic_and_level_roundtrip():
    tank = CapsuleTank(1.5, 3.0)
    h = np.linspace(0, 3.0, 500)
    assert np.all(np.diff(tank.volume(h)) > 0)
    h_test = np.linspace(0.05, 2.95, 30)
    np.testing.assert_allclose(tank.level(tank.volume(h_test)), h_test, atol=1e-4)


# ---------------------------------------------------------------- 열유속 / 진공

NOMINAL = dict(N=40, Nbar=20, eps=0.03, P_pa=1e-3, Th=300.0, Tc=T_C)


def test_flux_typical_magnitude():
    q = mli_heat_flux(**NOMINAL)
    assert 0.1 < q < 2.0, f"일반적인 MLI 열유속 범위(0.1~2 W/m²) 밖: {q:.3f}"


def test_flux_zero_without_temperature_difference():
    assert mli_heat_flux(**{**NOMINAL, "Th": T_C}) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("key, lo, hi, increases", [
    ("N", 20, 60, False),       # 적층수 ↑ → 열유속 ↓
    ("eps", 0.02, 0.06, True),  # 방사율 ↑ → ↑
    ("P_pa", 1e-4, 1e-1, True), # 진공 악화 → ↑
    ("Th", 250, 320, True),     # 외부 온도 ↑ → ↑
    ("Nbar", 10, 30, True),     # 적층밀도 ↑ → 고체 전도 ↑
])
def test_flux_trends(key, lo, hi, increases):
    q_lo = mli_heat_flux(**{**NOMINAL, key: lo})
    q_hi = mli_heat_flux(**{**NOMINAL, key: hi})
    assert (q_hi > q_lo) == increases


def test_vacuum_pressure_limits():
    Pv0, G, S, V = 1e-1, 1e-8, 1e-3, 2.0
    assert vacuum_pressure(0.0, Pv0, G, S, V) == pytest.approx(Pv0)
    assert vacuum_pressure(1e9, Pv0, G, S, V) == pytest.approx(G / S)
    t = np.linspace(0, 5 * V / S, 100)  # 시간상수의 5배 구간 (이후는 평형이라 diff=0)
    assert np.all(np.diff(vacuum_pressure(t, Pv0, G, S, V)) < 0)       # 초기압 > 평형압 → 감소
    assert np.all(np.diff(vacuum_pressure(t, 1e-7, G, S, V)) > 0)      # 초기압 < 평형압 → 증가


# ---------------------------------------------------------------- 보일오프 ODE

def _loss(p):
    return 1 - simulate(p)[1][-1]


def test_curve_basic_shape():
    t, ratio = simulate(DesignParams())
    assert t[0] == 0 and t[-1] == pytest.approx(365)
    assert ratio[0] == pytest.approx(1.0)
    assert np.all(np.diff(ratio) <= 1e-12)
    assert np.all((ratio >= 0) & (ratio <= 1))


def test_daily_boiloff_rate_plausible():
    t, ratio = simulate(DesignParams())
    rate = (1 - ratio[-1]) / t[-1] * 100
    assert 0.05 < rate < 2.0, f"일일 보일오프율 {rate:.3f} %/day"


def test_mass_balance():
    """ODE 결과의 질량 감소량 = ∫Q_L dt / h_fg (독립 적분으로 검산)."""
    model = BoiloffModel(DesignParams(Pv0=1e-1))
    # 진공 과도 시간상수(약 2,300 s)보다 촘촘한 격자(약 130 s)로 검산
    t_day, ratio = model.simulate(n_points=20000)
    t, m = t_day * DAY, ratio * model.m0
    Q = np.array([model.heat_to_liquid(ti, mi) for ti, mi in zip(t, m)])
    assert model.m0 - m[-1] == pytest.approx(trapezoid(Q, t) / H_FG, rel=1e-4)


@pytest.mark.parametrize("change, more_loss", [
    (dict(N=80), False),
    (dict(eps=0.06), True),
    (dict(Pv0=1e-1, G_out=1e-6, S=1e-4), True),  # 진공 악화
    (dict(G_sup=1e-1), True),
    (dict(R=0.5), True),                          # 작은 탱크 → 비표면적 ↑
])
def test_design_trends(change, more_loss):
    base = _loss(DesignParams())
    changed = _loss(replace(DesignParams(), **change))
    assert (changed > base) == more_loss


def _chord_deviation(ratio):
    """시작점과 끝점을 잇는 직선에서 벗어난 최대 편차 / 전체 감소량."""
    chord = np.linspace(ratio[0], ratio[-1], len(ratio))
    return np.max(np.abs(ratio - chord)) / (ratio[0] - ratio[-1])


def test_curve_is_nonlinear_for_small_tank():
    """소형 탱크는 액위가 내려가며 젖음 면적이 줄어 감소 속도가 둔화된다."""
    _, ratio = simulate(DesignParams(R=1.0, LD=0.0))
    assert ratio[-1] > 0                        # 소진 없이 순수 형상 효과만 확인
    assert _chord_deviation(ratio) > 0.05
    slope = -np.diff(ratio)
    assert slope[-1] < 0.8 * slope[5]          # 후반 감소 속도가 초반보다 느림


def test_large_tank_still_curved():
    _, ratio = simulate(DesignParams(R=2.5, LD=2.0))
    assert _chord_deviation(ratio) > 0.01


def test_fill_ratio_affects_normalized_curve():
    lo = _loss(DesignParams(fill=0.5))
    hi = _loss(DesignParams(fill=0.95))
    assert lo != pytest.approx(hi, rel=1e-3)


def test_sphere_runs():
    t, ratio = simulate(DesignParams(LD=0.0))
    assert 0 < ratio[-1] < 1


def test_depletion_stops_at_zero():
    """극단 조건(작은 탱크, 나쁜 진공)에서 소진 후 0으로 유지, 음수 없음."""
    p = DesignParams(R=0.2, LD=0.0, N=10, Pv0=10.0, G_out=1e-4, S=1e-4, G_sup=1.0, fill=0.5)
    _, ratio = simulate(p)
    assert ratio[-1] == 0.0
    assert np.all(ratio >= 0)
    assert np.all(np.diff(ratio) <= 1e-12)

# ---------------------------------------------------------------- simulate_detailed (specs/001 T004)

DEPLETING = DesignParams(R=0.3, N=10, Pv0=1e-1, G_out=1e-6, S=1e-4, LD=0.0, fill=0.5)


def test_simulate_detailed_depletion_time():
    """소진 시각 t_empty [day]가 유한하고, 이후 격자는 0, 격자 첫 0 시점과 격자 간격 이내."""
    t, ratio, t_empty = BoiloffModel(DEPLETING).simulate_detailed()
    assert np.isfinite(t_empty)
    after = t > t_empty
    assert np.any(after)                       # 비교 대상 격자 시점이 실제로 있어야 함
    assert np.all(ratio[after] == 0.0)
    first_zero = t[np.nonzero(ratio == 0.0)[0][0]]
    grid_step = 365.0 / 99                     # 격자 간격 [day]
    assert abs(first_zero - t_empty) <= grid_step

    # 촘촘한 격자로 소진 구간 [t_a, t_b]를 독립적으로 구한다(검증 2회차 발견 #1).
    t_f, ratio_f, _ = BoiloffModel(DEPLETING).simulate_detailed(n_points=20001)
    i_zero = np.nonzero(ratio_f == 0.0)[0][0]  # 처음 0이 되는 촘촘한 격자 시점
    assert i_zero > 0 and ratio_f[i_zero - 1] > 0.0
    t_a, t_b = t_f[i_zero - 1], t_f[i_zero]   # 마지막 양수 시점, 처음 0 시점 [day]
    tol = 0.05                                 # [day]

    def in_bracket(v):
        return t_a - tol <= v <= t_b + tol

    assert in_bracket(t_empty), (t_empty, t_a, t_b)
    # 판별력 확인: 격자 근사값이나 ±2일 어긋난 값은 이 검사를 통과하지 못해야 한다.
    assert not in_bracket(first_zero), (first_zero, t_a, t_b)
    assert not in_bracket(t_empty + 2.0)
    assert not in_bracket(t_empty - 2.0)


def test_simulate_detailed_no_depletion():
    _, ratio, t_empty = BoiloffModel(DesignParams()).simulate_detailed()
    assert t_empty == np.inf
    assert ratio[-1] > 0


REFERENCE = Path(__file__).resolve().parent / "data" / "simulate_reference.npz"


def test_simulate_matches_reference():
    """T007 이전 simulate() 출력(고정 기준값, tests/data/README.md)과 비트 단위로 같다."""
    ref = np.load(REFERENCE, allow_pickle=False)
    fields = [str(f) for f in ref["design_fields"]]
    days_s, n_s = float(ref["short_days"]), int(ref["short_n_points"])
    assert ref["designs"].shape[0] == 33
    for i, row in enumerate(ref["designs"]):
        p = DesignParams(**dict(zip(fields, row)))
        model = BoiloffModel(p)
        for t, ratio in (simulate(p), model.simulate_detailed()[:2]):
            assert np.array_equal(t, ref["t_default"][i]), f"design {i}: t (default)"
            assert np.array_equal(ratio, ref["ratio_default"][i]), f"design {i}: ratio (default)"
        for t, ratio in (simulate(p, days_s, n_s), model.simulate_detailed(days_s, n_s)[:2]):
            assert np.array_equal(t, ref["t_short"][i]), f"design {i}: t (short)"
            assert np.array_equal(ratio, ref["ratio_short"][i]), f"design {i}: ratio (short)"
