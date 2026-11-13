"""샘플 시뮬레이션·품질 필터 테스트 (specs/001 T012): run_sample, validate_curve (research R6)."""
import numpy as np
import pytest

from data.config import DEFAULT_INPUTS, GenerationConfig
from data.simulate import Rejection, SampleResult, run_sample, validate_curve
from physics import BoiloffModel, DesignParams

NAMES = [s.name for s in DEFAULT_INPUTS]
CFG = GenerationConfig()
DEPLETING = DesignParams(R=0.3, N=10, Pv0=1e-1, G_out=1e-6, S=1e-4, LD=0.0, fill=0.5)


def _x(p: DesignParams) -> np.ndarray:
    return np.array([float(getattr(p, n)) for n in NAMES])


def _good_curve(n=100):
    return np.linspace(1.0, 0.5, n)


# ---------------------------------------------------------------- ① 기본 설계

def test_default_design_outputs():
    p = DesignParams()
    res = run_sample(_x(p), DEFAULT_INPUTS, CFG)
    assert isinstance(res, SampleResult)
    model = BoiloffModel(p)
    Y, aux = res.Y, res.aux
    assert Y.shape == (100,)
    assert Y[0] == 1.0
    assert aux.shape == (5,)
    Q0, m0, m_lost, A_mli, t_empty = aux                     # 순서: Q0, m0, m_lost, A_mli, t_empty
    assert m0 == model.m0
    assert m_lost == m0 * (1 - Y[-1])
    assert A_mli == model.tank.A_tot
    assert Q0 == model.heat_to_liquid(0, model.m0)
    assert t_empty == np.inf
    assert res.depleted is False or res.depleted == np.False_
    # 곡선은 물리 모델 출력과 같다(첫 값 보정 제외)
    _, ratio, _ = model.simulate_detailed(CFG.days, CFG.n_points)
    assert np.array_equal(Y[1:], ratio[1:])


def _patch_curve(monkeypatch, y0):
    """simulate_detailed가 첫 값만 y0인 곡선을 돌려주게 한다(ODE의 1 − 2e-16 재현)."""
    orig = BoiloffModel.simulate_detailed

    def fake(self, days=365.0, n_points=100):
        t, ratio, t_empty = orig(self, days, n_points)
        ratio = ratio.copy()
        ratio[0] = y0
        return t, ratio, t_empty
    monkeypatch.setattr(BoiloffModel, "simulate_detailed", fake)


@pytest.mark.parametrize("y0", [1 - 2e-16, 1 - 1e-13, 1 + 1e-13, 1 - 9e-13])
def test_initial_value_snapped_to_one(monkeypatch, y0):
    """ODE가 t=0에서 1 − 2e-16 같은 값을 돌려줘도 Y[0]은 정확히 1.0(T016)."""
    _patch_curve(monkeypatch, y0)
    res = run_sample(_x(DesignParams()), DEFAULT_INPUTS, CFG)
    assert isinstance(res, SampleResult)
    assert res.Y[0] == 1.0


@pytest.mark.parametrize("y0", [1 - 1e-10, 1 - 1e-6, 1 + 1e-11])
def test_initial_value_far_from_one_rejected(monkeypatch, y0):
    _patch_curve(monkeypatch, y0)
    res = run_sample(_x(DesignParams()), DEFAULT_INPUTS, CFG)
    assert isinstance(res, Rejection)
    assert res.reason == "initial_not_one"
    assert "Y[0]" in res.detail


def test_initial_value_exact_one_unchanged_for_real_designs():
    """보정이 실제로 필요한 사례가 존재한다는 전제 확인 겸, 무작위 설계에서 항상 Y[0] == 1.0."""
    rng = np.random.default_rng(5)
    from data.sampling import sample_inputs
    X = sample_inputs(DEFAULT_INPUTS, 60, rng)
    raw_not_one = 0
    for x in X:
        res = run_sample(x, DEFAULT_INPUTS, CFG)
        assert isinstance(res, SampleResult)
        assert res.Y[0] == 1.0
        p = DesignParams(**dict(zip(NAMES, x)), **CFG.fixed)
        raw_not_one += BoiloffModel(p).simulate_detailed()[1][0] != 1.0
    assert raw_not_one > 0  # 물리 모델 원래 출력에 1.0이 아닌 첫 값이 실제로 있음


# ---------------------------------------------------------------- ② 소진 설계

def test_depleting_design():
    res = run_sample(_x(DEPLETING), DEFAULT_INPUTS, CFG)
    assert isinstance(res, SampleResult)
    t = np.linspace(0, CFG.days, CFG.n_points)
    t_empty = res.aux[4]
    assert np.isfinite(t_empty)
    assert bool(res.depleted) is True
    after = t > t_empty
    assert np.any(after)
    assert np.all(res.Y[after] == 0.0)
    assert res.aux[2] == res.aux[1]          # m_lost == m0 (FR-007)


# ---------------------------------------------------------------- ③ validate_curve 사유 코드

def test_validate_curve_ok():
    assert validate_curve(_good_curve()) is None
    flat = np.ones(100)
    assert validate_curve(flat) is None
    tiny_rise = _good_curve()
    tiny_rise[50] = tiny_rise[49] + 5e-10    # 1e-9 이하 증가는 허용
    assert validate_curve(tiny_rise) is None


@pytest.mark.parametrize("mutate, reason", [
    (lambda y: y.__setitem__(10, np.nan), "nan"),
    (lambda y: y.__setitem__(10, np.inf), "nan"),
    (lambda y: y.__setitem__(slice(90, None), -1e-3), "negative"),
    (lambda y: y.__setitem__(0, 1 + 2e-9), "above_one"),
    (lambda y: y.__setitem__(50, y[49] + 2e-9), "increasing"),
    (lambda y: y.__setitem__(0, 1 - 1e-10), "initial_not_one"),
])
def test_validate_curve_reasons(mutate, reason):
    y = _good_curve()
    mutate(y)
    out = validate_curve(y)
    assert out is not None
    assert out[0] == reason
    assert isinstance(out[1], str) and out[1]


def test_validate_curve_increasing_detail_has_index():
    y = _good_curve()
    y[50] = y[49] + 1e-3
    reason, detail = validate_curve(y)
    assert reason == "increasing"
    assert "50" in detail or "49" in detail


# ---------------------------------------------------------------- ④ solver_error

def test_solver_error(monkeypatch):
    def boom(self, *a, **k):
        raise RuntimeError("solver blew up")
    monkeypatch.setattr(BoiloffModel, "simulate_detailed", boom)
    res = run_sample(_x(DesignParams()), DEFAULT_INPUTS, CFG)
    assert isinstance(res, Rejection)
    assert res.reason == "solver_error"
    assert "solver blew up" in res.detail


def test_keyboard_interrupt_propagates(monkeypatch):
    def interrupt(self, *a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(BoiloffModel, "simulate_detailed", interrupt)
    with pytest.raises(KeyboardInterrupt):
        run_sample(_x(DesignParams()), DEFAULT_INPUTS, CFG)


def test_nan_aux_rejected(monkeypatch):
    """보조 출력에 NaN이 있으면 nan 사유로 제외(research R6). t_empty의 +inf는 정상."""
    monkeypatch.setattr(BoiloffModel, "heat_to_liquid", lambda self, t, m: float("nan"))
    monkeypatch.setattr(BoiloffModel, "simulate_detailed",
                        lambda self, days=365.0, n_points=100: (np.linspace(0, days, n_points),
                                                                np.linspace(1, 0.5, n_points), np.inf))
    res = run_sample(_x(DesignParams()), DEFAULT_INPUTS, CFG)
    assert isinstance(res, Rejection)
    assert res.reason == "nan"


# ---------------------------------------------------------------- ⑤ 설정 반영

def test_config_days_and_n_points_applied():
    cfg = GenerationConfig(days=100.0, n_points=37)
    p = DesignParams()
    res = run_sample(_x(p), DEFAULT_INPUTS, cfg)
    assert isinstance(res, SampleResult)
    assert res.Y.shape == (37,)
    _, ratio, _ = BoiloffModel(p).simulate_detailed(100.0, 37)
    assert np.array_equal(res.Y[1:], ratio[1:]) and res.Y[0] == 1.0
    assert abs(ratio[0] - 1.0) <= 1e-12
    # 기본 설정(365일, 100점)의 결과와 다르다
    base = run_sample(_x(p), DEFAULT_INPUTS, CFG)
    assert base.Y[-1] < res.Y[-1]


def test_config_fixed_applied():
    p = DesignParams()
    res280 = run_sample(_x(p), DEFAULT_INPUTS, GenerationConfig(fixed={"Th": 280.0}))
    res300 = run_sample(_x(p), DEFAULT_INPUTS, GenerationConfig(fixed={"Th": 300.0}))
    m280 = BoiloffModel(DesignParams(Th=280.0))
    _, ratio, t_empty = m280.simulate_detailed()
    assert np.array_equal(res280.Y[1:], ratio[1:])
    assert res280.aux[0] == m280.heat_to_liquid(0.0, m280.m0)
    assert res280.aux[0] != res300.aux[0]
    assert not np.array_equal(res280.Y, res300.Y)
