"""LHS 입력 샘플링 테스트 (specs/001 T011): sample_inputs(inputs, n, rng) -> ndarray (n, 10)."""
import dataclasses

import numpy as np
import pytest

from data.config import DEFAULT_INPUTS
from data.sampling import sample_inputs

NAMES = [s.name for s in DEFAULT_INPUTS]
IDX = {n: i for i, n in enumerate(NAMES)}


def _sample(n, seed=0, inputs=DEFAULT_INPUTS):
    return sample_inputs(inputs, n, np.random.default_rng(seed))


def test_shape_and_bounds():
    """① 모든 값이 [lo, hi] 안에 있다."""
    X = _sample(1000)
    assert X.shape == (1000, 10)
    assert X.dtype == np.float64
    for j, s in enumerate(DEFAULT_INPUTS):
        assert np.all(X[:, j] >= s.lo), s.name
        assert np.all(X[:, j] <= s.hi), s.name


def test_integer_column_and_endpoints():
    """② N 열은 정수값이고 n=2000이면 양 끝 10, 120이 모두 나온다(research R3)."""
    X = _sample(2000)
    N = X[:, IDX["N"]]
    assert np.all(N == np.floor(N))
    assert N.min() == 10 and N.max() == 120
    # 끝값이 다른 정수와 비슷한 빈도(반올림 방식이면 절반): 기대 2000/111 ≈ 18
    counts = np.bincount(N.astype(int), minlength=121)[10:121]
    assert counts[0] >= 12 and counts[-1] >= 12
    assert np.all(counts > 0)


def test_ten_bin_coverage():
    """③ n=1000, 각 입력을 10구간으로 나누면(로그 변수는 log10 구간) 모든 구간에 샘플이 있다(SC-005)."""
    X = _sample(1000)
    for j, s in enumerate(DEFAULT_INPUTS):
        col = X[:, j]
        if s.scale == "log":
            col, lo, hi = np.log10(col), np.log10(s.lo), np.log10(s.hi)
        else:
            lo, hi = s.lo, s.hi
        edges = np.linspace(lo, hi, 11)
        counts, _ = np.histogram(col, bins=edges)
        assert np.all(counts > 0), (s.name, counts)


def test_log_variables_uniform_in_log_space():
    """④ 로그 변수의 log10 평균이 구간 중앙과 ±0.05 decade 이내."""
    X = _sample(1000)
    for j, s in enumerate(DEFAULT_INPUTS):
        if s.scale != "log":
            continue
        mid = 0.5 * (np.log10(s.lo) + np.log10(s.hi))
        assert abs(np.log10(X[:, j]).mean() - mid) <= 0.05, s.name
        # 선형 공간에서 뽑았다면 log10 평균이 상한 쪽으로 크게 치우친다: 하위 절반(로그) 구간에 약 50%
        assert 0.4 <= np.mean(np.log10(X[:, j]) < mid) <= 0.6, s.name


def test_reproducible_with_same_seed():
    """⑤ 같은 시드의 Generator로 두 번 뽑으면 array_equal."""
    assert np.array_equal(_sample(500, seed=7), _sample(500, seed=7))
    assert not np.array_equal(_sample(500, seed=7), _sample(500, seed=8))


def test_scale_change_to_linear():
    """⑥ G_sup 스케일을 linear로 바꾸면 선형 분포(산술 평균이 구간 중앙과 폭의 5% 이내)."""
    inputs = [dataclasses.replace(s, scale="linear") if s.name == "G_sup" else s for s in DEFAULT_INPUTS]
    s = inputs[IDX["G_sup"]]
    col = _sample(1000, inputs=inputs)[:, IDX["G_sup"]]
    assert abs(col.mean() - 0.5 * (s.lo + s.hi)) <= 0.05 * (s.hi - s.lo)
    # 기본(log) 스케일이면 이 조건을 만족하지 않는다(판별력 확인)
    col_log = _sample(1000)[:, IDX["G_sup"]]
    assert abs(col_log.mean() - 0.5 * (s.lo + s.hi)) > 0.05 * (s.hi - s.lo)


def test_lhs_stratification_n10():
    """⑦ n=10이면 정수가 아닌 각 입력의 10개 등구간(로그 변수는 log10)에 정확히 1개씩(LHS 층화)."""
    for seed in range(5):
        X = _sample(10, seed=seed)
        for j, s in enumerate(DEFAULT_INPUTS):
            if s.scale == "int":
                continue
            col = X[:, j]
            if s.scale == "log":
                col, lo, hi = np.log10(col), np.log10(s.lo), np.log10(s.hi)
            else:
                lo, hi = s.lo, s.hi
            counts, _ = np.histogram(col, bins=np.linspace(lo, hi, 11))
            assert counts.tolist() == [1] * 10, (seed, s.name, counts)
