"""학습/검증/테스트 분할 (specs/001 research R7, FR-012).

n_train = round(r0·n), n_val = round(r1·n), n_test = n − n_train − n_val.
rng.permutation(n) 순서대로 0(train) / 1(val) / 2(test)를 매긴다.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np


def split_labels(n: int, ratios: Sequence[float], rng: np.random.Generator) -> np.ndarray:
    """길이 n의 세트 라벨(int8: 0 = train, 1 = val, 2 = test)."""
    r0, r1, _ = (float(r) for r in ratios)
    n_train = int(round(r0 * n))
    n_val = int(round(r1 * n))
    if n_train + n_val > n:  # 비율 합이 1이면 일어나지 않지만 음수 test 크기를 막는다
        raise ValueError(f"분할 크기 오류: n={n}, train={n_train}, val={n_val}")
    order = rng.permutation(n)
    labels = np.full(n, 2, dtype=np.int8)
    labels[order[:n_train]] = 0
    labels[order[n_train:n_train + n_val]] = 1
    return labels
