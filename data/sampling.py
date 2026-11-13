"""Latin Hypercube 입력 샘플링 (specs/001 research R2·R3, FR-001·003·004).

단위 샘플 u ∈ [0,1)^d를 LHS로 뽑은 뒤 변수별로 물리 단위로 변환한다.
- linear: x = lo + u·(hi − lo)
- log:    x = 10^(log10 lo + u·(log10 hi − log10 lo))
- int:    x = clip(lo + floor(u·(hi − lo + 1)), lo, hi)   # 양 끝 정수도 같은 확률
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
from scipy.stats import qmc

from data.config import InputSpec


def sample_inputs(inputs: Sequence[InputSpec], n: int, rng: np.random.Generator) -> np.ndarray:
    """LHS 샘플 n개를 물리 단위로 돌려준다. 반환: float64 (n, len(inputs)), 열 순서 = inputs 순서."""
    U = qmc.LatinHypercube(d=len(inputs), rng=rng).random(n)
    X = np.empty_like(U, dtype=np.float64)
    for j, s in enumerate(inputs):
        u = U[:, j]
        lo, hi = float(s.lo), float(s.hi)
        if s.scale == "linear":
            X[:, j] = lo + u * (hi - lo)
        elif s.scale == "log":
            a, b = np.log10(lo), np.log10(hi)
            X[:, j] = 10.0 ** (a + u * (b - a))
        elif s.scale == "int":
            X[:, j] = np.clip(lo + np.floor(u * (hi - lo + 1.0)), lo, hi)
        else:  # InputSpec 검증을 통과했다면 오지 않는다
            raise ValueError(f"{s.name}: 알 수 없는 scale {s.scale!r}")
    return X
