"""pytest 공통 설정: 저장소 루트를 import 경로 맨 앞에 둔다 (specs/001 T003)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

import numpy as np
import pytest


@pytest.fixture(scope="session")
def small_dataset(tmp_path_factory):
    """n=300, seed=1로 임시 디렉터리에 만든 데이터셋 경로 (specs/001 T020). US2·US3 테스트가 쓴다."""
    from data.config import GenerationConfig
    from data.generate import generate
    out = tmp_path_factory.mktemp("small_dataset")
    return generate(GenerationConfig(n_requested=300, seed=1), out)


class ODESurrogate:
    """ODE를 그대로 감싼 가짜 대리모델 (specs/003 research R11). 002 계약과 같은 API:
    predict, check_range, t, train_range, input_names. 같은 입력 행은 캐시한다(속도용, 값은 ODE 그대로)."""

    def __init__(self):
        from data.config import DEFAULT_INPUTS
        self.input_names = [s.name for s in DEFAULT_INPUTS]
        self._lo = np.array([float(s.lo) for s in DEFAULT_INPUTS])
        self._hi = np.array([float(s.hi) for s in DEFAULT_INPUTS])
        self.t = np.linspace(0.0, 365.0, 100)
        self._cache = {}
        self.calls = 0

    @property
    def train_range(self):
        return {"names": list(self.input_names), "lo": self._lo.tolist(), "hi": self._hi.tolist()}

    def _as_2d(self, X):
        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1:
            X = X[None, :]
        if X.ndim != 2 or X.shape[1] != len(self.input_names):
            raise ValueError(f"X는 (n, {len(self.input_names)}) 이어야 함: shape {X.shape}")
        return X

    def check_range(self, X):
        from surrogate import OutOfRangeError
        X = self._as_2d(X)
        ok = (X >= self._lo) & (X <= self._hi)
        if not ok.all():
            i, j = np.argwhere(~ok)[0]
            raise OutOfRangeError(self.input_names[j], float(X[i, j]), float(self._lo[j]), float(self._hi[j]))

    def predict(self, X):
        from physics import DesignParams, simulate
        X = self._as_2d(X)
        self.check_range(X)
        out = []
        for row in X:
            key = row.tobytes()
            if key not in self._cache:
                self.calls += 1
                p = DesignParams(**dict(zip(self.input_names, map(float, row))))
                self._cache[key] = simulate(p, days=365.0, n_points=100)[1]
            out.append(self._cache[key])
        return np.array(out)


@pytest.fixture(scope="session")
def ode_sur():
    return ODESurrogate()
