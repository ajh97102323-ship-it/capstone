"""surrogate/features.py 테스트 (specs/002 T002, research R2, data-model 1절)."""
import time

import numpy as np
import pytest

from data.config import DEFAULT_INPUTS
from data.sampling import sample_inputs
from physics import BoiloffModel, CapsuleTank, DesignParams
from physics.model import H_FG
from surrogate import features as F

NAMES = [s.name for s in DEFAULT_INPUTS]


def _designs(n, seed):
    return sample_inputs(DEFAULT_INPUTS, n, np.random.default_rng(seed))


def test_feature_layout_and_log_columns():
    """① 특성 11개, 순서는 input_names + log10_k, 로그 스케일 4개는 log10."""
    X = _designs(20, 0)
    Z = F.build_features(X, NAMES)
    assert Z.shape == (20, 11)
    assert list(F.FEATURE_NAMES) == NAMES + ["log10_k"]
    log_cols = {"G_sup", "Pv0", "G_out", "S"}
    assert set(F.LOG_INPUTS) == log_cols
    for j, nm in enumerate(NAMES):
        expect = np.log10(X[:, j]) if nm in log_cols else X[:, j]
        np.testing.assert_allclose(Z[:, j], expect, rtol=1e-14, atol=0)
    assert np.all(np.isfinite(Z))


def test_k_matches_boiloff_model_including_depleted_designs():
    """② 무작위 50개(소진 포함)에서 k가 BoiloffModel 기반 값과 상대 1e-3 이내."""
    X = _designs(50, 3)
    k = F.initial_evaporation_rate(X, NAMES)
    ref = np.empty(len(X))
    for i, x in enumerate(X):
        m = BoiloffModel(DesignParams(**dict(zip(NAMES, x))))
        ref[i] = m.heat_to_liquid(0.0, m.m0) / (H_FG * m.m0) * 86400.0  # [1/day]
    np.testing.assert_allclose(k, ref, rtol=1e-3)
    assert np.all(k > 0)
    # 소진 설계(k가 큰 쪽)가 실제로 섞여 있는지: 1년 안에 다 증발하려면 k > 1/365
    assert (k > 1 / 365).any() and (k < 1 / 365).any()
    # log10_k 열도 같은 값
    Z = F.build_features(X, NAMES)
    np.testing.assert_allclose(10 ** Z[:, -1], k, rtol=1e-12)


def test_k_respects_external_temperature():
    X = _designs(5, 4)
    k300 = F.initial_evaporation_rate(X, NAMES, Th=300.0)
    k250 = F.initial_evaporation_rate(X, NAMES, Th=250.0)
    assert np.all(k250 < k300)
    m = BoiloffModel(DesignParams(**dict(zip(NAMES, X[0])), Th=250.0))
    ref = m.heat_to_liquid(0.0, m.m0) / (H_FG * m.m0) * 86400.0
    assert k250[0] == pytest.approx(ref, rel=1e-3)


def test_wetted_fraction_table_matches_capsule_tank():
    """③ w 표 값이 CapsuleTank로 직접 계산한 값과 1e-3 이내 (격자점이 아닌 임의 점)."""
    rng = np.random.default_rng(5)
    fill = rng.uniform(0.5, 0.95, 200)
    ld = rng.uniform(0.0, 3.0, 200)
    w = F.wetted_fraction(fill, ld)
    for i in range(200):
        tank = CapsuleTank(1.0, 2.0 * ld[i])
        ref = tank.wetted_area(tank.level(fill[i] * tank.V_tot)) / tank.A_tot
        assert abs(w[i] - ref) < 1e-3
    # 경계(학습 범위 끝)도 계산된다
    edge = F.wetted_fraction(np.array([0.5, 0.95, 0.5, 0.95]), np.array([0.0, 0.0, 3.0, 3.0]))
    assert np.all((edge > 0) & (edge < 1))


def test_wrong_input_order_or_shape_raises():
    """④ 입력 순서·이름·열 수가 다르면 ValueError."""
    X = _designs(3, 6)
    swapped = NAMES.copy()
    swapped[0], swapped[1] = swapped[1], swapped[0]
    with pytest.raises(ValueError):
        F.build_features(X, swapped)
    with pytest.raises(ValueError):
        F.build_features(X, NAMES[:-1])
    with pytest.raises(ValueError):
        F.build_features(X[:, :9], NAMES[:9])
    with pytest.raises(ValueError):
        F.build_features(X[0], NAMES)  # 2차원이 아님
    with pytest.raises(ValueError):
        F.initial_evaporation_rate(X, swapped)


def test_nonpositive_log_input_raises():
    X = _designs(3, 7)
    X[1, NAMES.index("S")] = 0.0
    with pytest.raises(ValueError):
        F.build_features(X, NAMES)


def test_features_for_1000_designs_under_50ms():
    """⑤ 1000개 특성 계산이 50 ms 이내(배열 계산)."""
    X = _designs(1000, 8)
    F.build_features(X, NAMES)  # 예열
    best = min(_time(lambda: F.build_features(X, NAMES)) for _ in range(5))
    assert best < 0.050, f"{best * 1e3:.1f} ms"


def _time(fn):
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0
